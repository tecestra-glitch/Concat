"""Build route candidates from the latest quotes, rank them and persist opportunities.

Quote semantics (contract): `buy`/`sell` are from the house's perspective, `buy` = the house buys
`base`. So a quote offers two conversions: base -> quote at `buy`, and quote -> base at `1/sell`.
`market_reference` quotes are never used as executable legs (only for valuation).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..config import SIMULATION_MODE
from ..decimal_utils import ONE, fmt
from ..engine.positions import Position
from ..engine.ranking import Candidate, Ranked, rank_opportunities
from ..engine.routes import Fee, RouteError, RouteResult, StepSpec, simulate_route
from ..engine.search import DEFAULT_AMOUNTS, Evaluation, SearchResult, adaptive_amount_search
from ..models import Opportunity, Quote, Simulation, utcnow
from ..schemas import OpportunityOut, PositionIn, SearchOut, SimulationRequest, SimulationResponse
from .quotes import is_reference, latest_quotes

NAMESPACE = uuid.UUID("3f1c0d2e-7b4a-4e0f-9c8d-2a6b5e4d3c21")
Objective = Literal["cycle", "remittance", "purchase"]
MAX_LEG_OPTIONS = 6
MAX_TRI_OPTIONS = 4
DURATION_BY_MODALITY = {
    "cash": "imediato (presencial)",
    "transfer": "0–2 dias úteis",
    "account": "imediato",
    "card_debit": "imediato",
    "card_credit": "até a fatura",
    "card_virtual": "imediato",
}


@dataclass(frozen=True, slots=True)
class Conversion:
    quote: Quote
    from_ccy: str
    to_ccy: str
    rate: Decimal  # to_ccy per 1 from_ccy
    side: Literal["buy", "sell"]

    @property
    def route_key(self) -> str:
        q = self.quote
        return f"{q.source_id}:{q.branch_id or '-'}:{q.context_hash or '-'}:{self.from_ccy}>{self.to_ccy}"

    @property
    def location(self) -> str:
        return self.quote.city or "digital"


def conversions_from_quotes(quotes: Iterable[Quote]) -> list[Conversion]:
    out: list[Conversion] = []
    for q in quotes:
        if is_reference(q):  # BCP/PTAX style references are valuation only (B23)
            continue
        if q.buy is not None and q.buy > 0:
            out.append(Conversion(q, q.base, q.quote, q.buy, "buy"))
        if q.sell is not None and q.sell > 0:
            out.append(Conversion(q, q.quote, q.base, ONE / q.sell, "sell"))
    return out


def pick_for_amount(convs: Iterable[Conversion], amount: Decimal) -> list[Conversion]:
    """One conversion per route key: the amount-specific quote when it exists, else the generic one.
    Providers that only publish other amounts are skipped (they do not support `amount`)."""
    groups: dict[str, list[Conversion]] = {}
    for c in convs:
        groups.setdefault(c.route_key, []).append(c)
    picked: list[Conversion] = []
    for key in sorted(groups):
        options = groups[key]
        exact = [c for c in options if c.quote.amount_base is not None and c.quote.amount_base == amount]
        generic = [c for c in options if c.quote.amount_base is None]
        chosen = exact or generic
        if chosen:
            picked.append(chosen[0])
    return picked


def supports_amount(quotes: Sequence[Quote], amount: Decimal) -> bool:
    return any(c.from_ccy == "BRL" for c in pick_for_amount(conversions_from_quotes(quotes), amount))


def _fees(q: Quote) -> tuple[Fee, ...]:
    fees = []
    for f in q.fees or []:
        amount = f.get("amount")
        fees.append(
            Fee(
                label=f.get("label", "tarifa"),
                amount=Decimal(str(amount)) if amount is not None else None,
                currency=f.get("currency", q.base),
            )
        )
    return tuple(fees)


def _context_summary(q: Quote) -> str:
    if not q.context:
        return ""
    parts = [f"{k}={v}" for k, v in sorted(q.context.items()) if v not in (None, "", False)]
    return f" [{', '.join(parts)}]" if parts else ""


def step_from_conversion(c: Conversion) -> StepSpec:
    q = c.quote
    pos_from = Position(currency=c.from_ccy, institution=q.source_id, location=c.location, modality=q.modality)
    pos_to = Position(currency=c.to_ccy, institution=q.source_id, location=c.location, modality=q.modality)
    if c.side == "buy":
        note = f"{c.to_ccy} por 1 {c.from_ccy} (compra {fmt(q.buy)}, {q.unit_note})"
    else:
        note = f"{c.to_ccy} por 1 {c.from_ccy} (1/venda {fmt(q.sell)}, {q.unit_note})"
    return StepSpec(
        description=f"{c.from_ccy}→{c.to_ccy} via {q.source_id} ({c.location}, {q.modality}){_context_summary(q)}",
        from_position=pos_from,
        to_position=pos_to,
        rate=c.rate,
        rate_note=note,
        fees=_fees(q),
        duration=DURATION_BY_MODALITY.get(q.modality, ""),
        promo=(q.context or {}).get("promo") if q.context else None,
        confidence="quoted" if q.kind == "executable" else "estimated",
        evidence_id=q.evidence_id,
    )


def _valuation_priority(q: Quote) -> int:
    """Lower wins. Third-party aggregators (dolarPy) are the last resort, never ahead of BCP (SEC-06)."""
    if q.channel == "aggregator" or q.modality == "reference":
        return 3
    if q.kind == "market_reference":
        return 0
    return 1 if q.channel == "digital" else 2


def _quote_mid(q: Quote) -> Decimal | None:
    if q.buy is not None and q.sell is not None:
        return (q.buy + q.sell) / 2
    if q.buy is not None or q.sell is not None:
        return q.buy if q.buy is not None else q.sell
    return None


def valuation_quotes(quotes: Iterable[Quote], valuation: str) -> dict[str, Quote]:
    """currency -> the quote that values it in `valuation` (the same choice as `derive_valuation_rates`)."""
    best: dict[str, tuple[tuple[int, str], Quote]] = {}
    for q in quotes:
        mid = _quote_mid(q)
        if mid is None or mid <= 0:
            continue
        if q.quote != valuation and q.base != valuation:
            continue
        ccy = q.base if q.quote == valuation else q.quote
        prio = (_valuation_priority(q), q.source_id or "")
        cur = best.get(ccy)
        if cur is None or prio < cur[0]:
            best[ccy] = (prio, q)
    return {k: v[1] for k, v in best.items()}


def derive_valuation_rates(quotes: Iterable[Quote], valuation: str) -> dict[str, Decimal]:
    """currency -> valuation units per 1 unit, preferring official market_reference mids (BCP); ties are
    broken by source_id so the result never depends on the order the quotes arrive in."""
    out: dict[str, Decimal] = {}
    for ccy, q in valuation_quotes(quotes, valuation).items():
        mid = _quote_mid(q)
        if mid is not None:
            out[ccy] = mid if q.quote == valuation else ONE / mid
    return out


def _by_pair(convs: Iterable[Conversion]) -> dict[tuple[str, str], list[Conversion]]:
    pairs: dict[tuple[str, str], list[Conversion]] = {}
    for c in convs:
        pairs.setdefault((c.from_ccy, c.to_ccy), []).append(c)
    for lst in pairs.values():
        lst.sort(key=lambda c: (-c.rate, c.route_key))
    return pairs


def _path_channel_city(path: Sequence[Conversion]) -> tuple[str, str | None]:
    for c in path:
        if c.quote.channel == "physical":
            return "physical", c.quote.city
    return "digital", None


def _candidate_id(kind: str, capital: Decimal, objective: str, route_key: str) -> str:
    return str(uuid.uuid5(NAMESPACE, f"{kind}|{fmt(capital)}|{objective}|{route_key}"))


def _route_key(path: Sequence[Conversion]) -> str:
    return " > ".join(c.route_key for c in path)


def _title_legs(path: Sequence[Conversion]) -> str:
    return " → ".join(f"{c.quote.source_id} ({c.location})" for c in path)


@dataclass(slots=True)
class BuildOptions:
    objective: Objective = "cycle"
    destination: PositionIn | None = None
    channels: tuple[str, ...] = ("digital", "physical")
    valuation_currency: str = "BRL"
    valuation_rates: dict[str, Decimal] = field(default_factory=dict)


def cycle_candidates(convs: Sequence[Conversion], capital: Decimal, opts: BuildOptions) -> list[Candidate]:
    pairs = _by_pair(convs)
    paths: list[tuple[Conversion, ...]] = []
    for mid in ("USD", "PYG"):
        for c1 in pairs.get(("BRL", mid), [])[:MAX_LEG_OPTIONS]:
            for c2 in pairs.get((mid, "BRL"), [])[:MAX_LEG_OPTIONS]:
                paths.append((c1, c2))
    for m1, m2 in (("PYG", "USD"), ("USD", "PYG")):
        for c1 in pairs.get(("BRL", m1), [])[:MAX_TRI_OPTIONS]:
            for c2 in pairs.get((m1, m2), [])[:MAX_TRI_OPTIONS]:
                for c3 in pairs.get((m2, "BRL"), [])[:MAX_TRI_OPTIONS]:
                    paths.append((c1, c2, c3))

    out: list[Candidate] = []
    for path in paths:
        channel, city = _path_channel_city(path)
        if channel not in opts.channels:
            continue
        try:
            res = simulate_route(
                [step_from_conversion(c) for c in path],
                capital,
                valuation_currency=opts.valuation_currency,
                valuation_rates=opts.valuation_rates,
            )
        except RouteError:
            continue
        if res.roi is None or res.cycle_profit is None or res.final_available is None:
            continue
        rk = _route_key(path)
        legs = "→".join([path[0].from_ccy, *(c.to_ccy for c in path)])
        out.append(
            Candidate(
                id=_candidate_id("cycle", capital, "cycle", rk),
                title=f"Ciclo {legs}: {_title_legs(path)}",
                kind="cycle",
                channel=channel,  # type: ignore[arg-type]
                city=city,
                capital=res.total_capital_allocated or capital,
                final_value=res.final_available,
                net_gain=res.cycle_profit,
                roi=res.roi,
                effective_rate=res.effective_rate,
                valuation_currency=opts.valuation_currency,
                steps=res.steps,
                confidence=res.confidence,
                pending_costs=res.pending_costs,
                objective="cycle",
                extra={"route_key": rk},
            )
        )
    return out


def saving_candidates(convs: Sequence[Conversion], capital: Decimal, opts: BuildOptions) -> list[Candidate]:
    dest = opts.destination
    dest_ccy = dest.currency if dest else "PYG"
    dest_loc = dest.location if dest else None
    kind = "remittance_saving" if opts.objective == "remittance" else "purchase_saving"
    pairs = _by_pair(convs)

    paths: list[tuple[Conversion, ...]] = [(c,) for c in pairs.get(("BRL", dest_ccy), [])[:MAX_LEG_OPTIONS]]
    for mid in ("USD", "PYG", "BRL"):
        if mid in ("BRL", dest_ccy):
            continue
        for c1 in pairs.get(("BRL", mid), [])[:MAX_TRI_OPTIONS]:
            for c2 in pairs.get((mid, dest_ccy), [])[:MAX_TRI_OPTIONS]:
                paths.append((c1, c2))

    sims: list[tuple[tuple[Conversion, ...], RouteResult]] = []
    for path in paths:
        last = path[-1]
        if opts.objective == "purchase" and dest_loc not in (None, "digital"):
            if last.quote.channel == "physical" and last.quote.city != dest_loc:
                continue
        channel, _ = _path_channel_city(path)
        if channel not in opts.channels:
            continue
        try:
            res = simulate_route([step_from_conversion(c) for c in path], capital, valuation_currency=None)
        except RouteError:
            continue
        sims.append((path, res))
    if not sims:
        return []

    complete = [s for s in sims if s[1].confidence != "incomplete"] or sims
    ref_path, ref = min(complete, key=lambda s: (s[1].net_credit, _route_key(s[0])))
    ref_rate = ref.net_credit / capital  # dest per 1 BRL via the reference (worst) route
    if ref_rate <= 0:
        return []

    out: list[Candidate] = []
    for path, res in sims:
        channel, city = _path_channel_city(path)
        final_value = res.net_credit / ref_rate
        net_gain = final_value - capital
        rk = _route_key(path)
        where = f" em {dest_loc}" if opts.objective == "purchase" and dest_loc else ""
        verb = "Remessa" if kind == "remittance_saving" else "Compra"
        out.append(
            Candidate(
                id=_candidate_id(kind, capital, opts.objective, rk),
                title=f"{verb} BRL→{dest_ccy}{where}: {_title_legs(path)}",
                kind=kind,  # type: ignore[arg-type]
                channel=channel,  # type: ignore[arg-type]
                city=city,
                capital=capital,
                final_value=final_value,
                net_gain=net_gain,
                roi=net_gain / capital,
                effective_rate=res.effective_rate,
                valuation_currency="BRL",
                steps=res.steps,
                confidence=res.confidence,
                pending_costs=res.pending_costs,
                objective=opts.objective,
                extra={
                    "route_key": rk,
                    "amount_out": fmt(res.net_credit),
                    "amount_out_currency": dest_ccy,
                    "reference_route": _title_legs(ref_path),
                    "reference_rate": fmt(ref_rate),
                },
            )
        )
    return out


def build_candidates(quotes: Sequence[Quote], capital: Decimal, opts: BuildOptions) -> list[Candidate]:
    convs = pick_for_amount(conversions_from_quotes(quotes), capital)
    if not opts.valuation_rates and opts.valuation_currency != "BRL":
        opts.valuation_rates = derive_valuation_rates(quotes, opts.valuation_currency)
    if opts.objective == "cycle":
        return cycle_candidates(convs, capital, opts)
    return saving_candidates(convs, capital, opts)


def evaluate_amount(quotes: Sequence[Quote], amount: Decimal, opts: BuildOptions) -> tuple[list[Ranked], Evaluation]:
    ranked = rank_opportunities(build_candidates(quotes, amount, opts))
    winner = next((r for r in ranked if r.in_main_ranking), None)
    ev = Evaluation(
        amount=amount,
        winner=winner.candidate.extra.get("route_key") if winner else None,
        roi=winner.candidate.roi if winner else None,
        payload=ranked,
    )
    return ranked, ev


def ranked_to_out(r: Ranked, *, data_mode: str, computed_at: datetime) -> OpportunityOut:
    data = r.to_dict()
    data.pop("rank", None)
    data.update({"computed_at": computed_at, "data_mode": data_mode})
    return OpportunityOut.model_validate(data)


def ranked_to_row(r: Ranked, *, data_mode: str, computed_at: datetime, simulation_id: str | None = None) -> Opportunity:
    c = r.candidate
    return Opportunity(
        id=c.id if simulation_id is None else str(uuid.uuid5(NAMESPACE, f"{simulation_id}|{c.id}")),
        title=c.title,
        kind=c.kind,
        channel=c.channel,
        city=c.city,
        objective=c.objective,
        capital_brl=c.capital,
        final_value_brl=c.final_value,
        net_gain_brl=c.net_gain,
        roi=c.roi,
        effective_rate=c.effective_rate,
        valuation_currency=c.valuation_currency,
        steps=[s.to_dict() for s in c.steps],
        confidence=c.confidence,
        pending_costs=list(c.pending_costs),
        in_main_ranking=r.in_main_ranking,
        ranking_reason=r.ranking_reason,
        comparable_best_digital_roi=r.comparable_best_digital_roi,
        computed_at=computed_at,
        simulation_id=simulation_id,
        data_mode=data_mode,
    )


def row_to_out(row: Opportunity) -> OpportunityOut:
    return OpportunityOut.model_validate(row)


@dataclass(slots=True)
class SimulationOutcome:
    ranked: list[Ranked]
    search: SearchResult
    response: SimulationResponse


def run_simulation(
    session: Session,
    req: SimulationRequest,
    *,
    data_mode: str,
    now: datetime | None = None,
    quotes: Sequence[Quote] | None = None,
) -> SimulationOutcome:
    now = now or utcnow()
    quotes = list(quotes) if quotes is not None else latest_quotes(session, data_mode=data_mode)
    opts = BuildOptions(
        objective=req.objective,
        destination=req.destination,
        channels=tuple(req.channels),
        valuation_currency=req.valuation_currency,
    )
    cache: dict[Decimal, list[Ranked]] = {}

    def evaluate(amount: Decimal) -> Evaluation:
        ranked, ev = evaluate_amount(quotes, amount, opts)
        cache[amount] = ranked
        return ev

    supports: Callable[[Decimal], bool] = lambda a: supports_amount(quotes, a)
    amounts = [Decimal(a) for a in req.amounts] if req.amounts else list(DEFAULT_AMOUNTS)
    search = adaptive_amount_search(evaluate, amounts=amounts, supports=supports)
    capital = Decimal(req.capital_brl)
    ranked = cache.get(capital) or evaluate_amount(quotes, capital, opts)[0]

    # D3: quotes come from the instance's mode, but everything a simulation produces is tagged
    # `simulation` (persisted rows keep `simulation_id`), so the standing ranking never sees it.
    simulation_id: str | None = None
    if req.persist:
        sim = Simulation(
            objective=req.objective,
            capital_brl=capital,
            request=req.model_dump(mode="json"),
            result=search.to_dict(),
            data_mode=SIMULATION_MODE,
            created_at=now,
        )
        session.add(sim)
        session.flush()
        simulation_id = sim.id
        for r in ranked:
            session.add(ranked_to_row(r, data_mode=SIMULATION_MODE, computed_at=now, simulation_id=simulation_id))
        session.flush()

    response = SimulationResponse(
        opportunities=[ranked_to_out(r, data_mode=SIMULATION_MODE, computed_at=now) for r in ranked],
        search=SearchOut.model_validate(search.to_dict()),
        simulation_id=simulation_id,
    )
    return SimulationOutcome(ranked=ranked, search=search, response=response)


def recompute_opportunities(
    session: Session,
    *,
    data_mode: str,
    now: datetime | None = None,
    capitals: Iterable[Decimal] = DEFAULT_AMOUNTS,
    objectives: Iterable[Objective] = ("cycle", "remittance"),
) -> list[Opportunity]:
    """Rebuild the standing ranking (rows with simulation_id NULL) from the latest quotes."""
    now = now or utcnow()
    quotes = latest_quotes(session, data_mode=data_mode)
    rows: list[Opportunity] = []
    for objective in objectives:
        opts = BuildOptions(objective=objective)
        for capital in capitals:
            ranked, _ = evaluate_amount(quotes, Decimal(capital), opts)
            rows.extend(ranked_to_row(r, data_mode=data_mode, computed_at=now) for r in ranked)
    session.execute(delete(Opportunity).where(Opportunity.data_mode == data_mode, Opportunity.simulation_id.is_(None)))
    session.add_all(rows)
    session.flush()
    return rows


def list_opportunities(
    session: Session,
    *,
    data_mode: str,
    capital: Decimal | None = None,
    channel: str | None = None,
    city: str | None = None,
    kind: str | None = None,
) -> list[Opportunity]:
    stmt = select(Opportunity).where(Opportunity.data_mode == data_mode, Opportunity.simulation_id.is_(None))
    if channel:
        stmt = stmt.where(Opportunity.channel == channel)
    if city:
        stmt = stmt.where(Opportunity.city == city)
    if kind:
        stmt = stmt.where(Opportunity.kind == kind)
    rows = list(session.scalars(stmt))
    if capital is not None:
        rows = [r for r in rows if r.capital_brl == capital]
    rows.sort(key=lambda r: (not r.in_main_ranking, -r.roi, -r.net_gain_brl, r.title))
    return rows


def opportunity_payload(rows: Sequence[Opportunity]) -> dict[str, Any]:
    return {
        "count": len(rows),
        "main_ranking": sum(1 for r in rows if r.in_main_ranking),
        "capitals": sorted({fmt(r.capital_brl) or "" for r in rows}),
    }
