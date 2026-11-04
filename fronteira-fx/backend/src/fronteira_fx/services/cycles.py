"""Position graph built from the latest quotes and the user's accounts (contract: `/v1/opportunities/cycles`).

Node = `<currency>@<venue>`; venue = source id (digital), `source:city` (exchange houses), account institution,
or `cash:<city>` (cash in one of the six cities: CDE, ASU, PJC, ENC, FOZ, PPO). Edges:
- quotes (base->quote at `buy`, quote->base at `1/sell`), with the spread measured against the mid;
- transfers between accounts and digital venues, and between accounts and exchange houses, priced by the trilhos in
  `data/rails.json` (no rail, or a rail with a null value => `incomplete`, never zero);
- walk-ins between cash and exchange houses in the same city (presencial);
- ATM moves (rail `->cash`, presencial);
- travel between cities (`data/transport.json`), one edge per currency and direction; a route with no cost is
  `incomplete`; a route that crosses the border sets `border` on the leg.

Amount windows (B16): a quote simulated for `amount_base` is valid from that amount up to (not including) the next
tier of the same family (source, branch, city, pair, modality, channel); `min_amount`/`max_amount` in the quote
context are explicit bounds. The search drops an edge whose window does not accept the amount reaching it.
Reference rates (`kind=market_reference` or `modality=reference`) are never edges (B23).

`enrich_cycle` adds what needs the valuation rates (BRL-based): gain in each currency, costs in the start currency,
and `requires_declaration` when a border leg moves more than US$ 10 000 (informs; never blocks).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import replace
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..decimal_utils import ONE, ZERO
from ..engine.graph import Cycle, Edge, Graph, find_cycles, node, node_currency
from ..engine.routes import Confidence
from ..models import Account, Quote
from .logistics import Rail, load_rails, load_transport
from .opportunities import derive_valuation_rates
from .quotes import is_reference, latest_quotes

CURRENCIES = ("BRL", "PYG", "USD")
CITIES = ("CDE", "ASU", "PJC", "ENC", "FOZ", "PPO")
DECLARATION_LIMIT_USD = Decimal(10_000)
TRANSFER_MINUTES_UNKNOWN = 240
ATM_MINUTES_UNKNOWN = 60
MINUTES_BY_MODALITY = {"cash": 15, "transfer": 240, "account": 5, "card_debit": 0, "card_credit": 0, "card_virtual": 0}
# smallest money unit: a tier covers [amount_base, next_tier - TIER_STEP] because Edge windows are inclusive
TIER_STEP = Decimal("0.01")
PROBE_AMOUNT = Decimal(1000)
# lugar digital -> endpoint de trilho (`data/rails.json`). Venue fora da tabela não tem trilho conhecido.
ENDPOINT_BY_VENUE = {
    "revolut": "revolut",
    "nomad": "nomad",
    "nubank": "br_bank",
    "brbank": "br_bank",
    "itau": "br_bank",
    "bradesco": "br_bank",
    "caixa": "br_bank",
    "banco_py": "py_bank",
}

Window = tuple[Decimal | None, Decimal | None]
Family = tuple[str, str | None, str | None, str, str, str, str]


def account_venue(a: Account) -> str:
    if a.kind == "cash" or (a.location in ("CDE", "ASU", "PJC") and a.institution in ("carteira", "cash")):
        return f"cash:{a.location}"
    return a.institution


def quote_venue(q: Quote) -> str:
    return f"{q.source_id}:{q.city}" if q.channel == "physical" and q.city else q.source_id


def endpoint_of_venue(venue: str) -> str | None:
    """Endpoint de trilho de um nó de lugar: caixa, casa de câmbio (`fonte:cidade`) ou banco/fintech conhecido."""
    if venue.startswith("cash:"):
        return "cash"
    if ":" in venue:
        return "exchange_house"
    return ENDPOINT_BY_VENUE.get(venue)


def valuation_rates(quotes: Iterable[Quote]) -> dict[str, Decimal]:
    """Moeda -> unidades de BRL por 1 unidade (BRL = 1). Base de toda conversão de custo e de ganho."""
    rates = derive_valuation_rates(quotes, "BRL")
    rates["BRL"] = ONE
    return rates


def convert(amount: Decimal | None, src: str, dst: str, rates: dict[str, Decimal]) -> Decimal | None:
    """`amount` de `src` em `dst` pelas taxas de valoração; None quando alguma moeda não tem taxa."""
    if amount is None:
        return None
    if src == dst:
        return amount
    if src in rates and dst in rates:
        return amount * rates[src] / rates[dst]
    return None


def _fee_terms(q: Quote, src_ccy: str, dst_ccy: str, rate: Decimal) -> tuple[Decimal, Decimal, Confidence]:
    """Return (fee_pct on the input, fee_fixed in dst currency, confidence).

    `incomplete` only when a cost is really unknown: a fee with neither amount nor pct, or a non-zero fee in a
    third currency that cannot be folded into the edge. Zero fees and percentage fees are known costs.
    """
    pct = ZERO
    fixed = ZERO
    conf: Confidence = "quoted" if q.kind == "executable" else "estimated"
    for f in q.fees or []:
        if f.get("pct") is not None:
            pct += Decimal(str(f["pct"]))
        amount = f.get("amount")
        if amount is None:
            if f.get("pct") is None:
                return pct, fixed, "incomplete"
            continue
        amt = Decimal(str(amount))
        if amt == 0:
            continue
        if f.get("currency") == src_ccy:
            fixed += amt * rate
        elif f.get("currency") == dst_ccy:
            fixed += amt
        else:
            return pct, fixed, "incomplete"
    return pct, fixed, conf


def _family(q: Quote) -> Family:
    return (q.source_id, q.branch_id, q.city, q.base, q.quote, q.modality, q.channel)


def _tier_ladders(quotes: Iterable[Quote]) -> dict[Family, list[Decimal]]:
    """Sorted distinct `amount_base` per quote family (the amounts a provider was simulated for)."""
    ladders: dict[Family, set[Decimal]] = {}
    for q in quotes:
        if q.amount_base is not None and not is_reference(q):
            ladders.setdefault(_family(q), set()).add(q.amount_base)
    return {k: sorted(v) for k, v in ladders.items()}


def _ctx_amount(ctx: dict[str, Any], key: str) -> Decimal | None:
    value = ctx.get(key)
    return Decimal(str(value)) if value not in (None, "") else None


def _window(q: Quote, ladders: dict[Family, list[Decimal]]) -> Window:
    """Amount window, in `q.base`, the quote is valid for. Explicit context bounds win; an amount-specific quote
    covers [amount_base, next tier); a generic quote (no amount) is unbounded."""
    ctx = q.context or {}
    lo, hi = _ctx_amount(ctx, "min_amount"), _ctx_amount(ctx, "max_amount")
    if q.amount_base is not None:
        if lo is None:
            lo = q.amount_base
        if hi is None:
            above = [a for a in ladders.get(_family(q), []) if a > q.amount_base]
            hi = above[0] - TIER_STEP if above else None
    return lo, hi


def _scale(window: Window, factor: Decimal) -> Window:
    lo, hi = window
    return (lo * factor if lo is not None else None, hi * factor if hi is not None else None)


def _edge_key(e: Edge) -> tuple:
    """Hashable, sortable identity: (src, dst, kind, window). Unbounded sorts before any bound."""
    return (e.src, e.dst, e.kind, e.min_in is not None, e.min_in or ZERO, e.max_in is None, e.max_in or ZERO)


def _best(edges: dict[tuple, Edge], e: Edge) -> None:
    """Keep the best edge per (src, dst, kind, amount window), compared at the window's lower bound."""
    key = _edge_key(e)
    cur = edges.get(key)
    probe = e.min_in if e.min_in is not None else PROBE_AMOUNT
    if cur is None or e.apply(probe) > cur.apply(probe):
        edges[key] = e


def _rail(rails: dict[str, Rail], src: str | None, dst: str | None, ccy: str, *, converts: bool) -> Rail | None:
    """Trilho de `src` para `dst` que sai em `ccy` (mesma moeda ou conversão). None quando não há."""
    if src is None or dst is None:
        return None
    for r in rails.values():
        if r.from_ == src and r.to == dst and r.currency == ccy and r.converts == converts:
            return r
    return None


def _rail_terms(
    rail: Rail | None, dst_ccy: str, src_endpoint: str | None, rates: dict[str, Decimal]
) -> tuple[Decimal, Decimal, Decimal, bool]:
    """(fee_pct, fee_fixed em dst, iof_pct, conhecido). Qualquer valor null vira `conhecido = False`."""
    if rail is None:
        return ZERO, ZERO, ZERO, False
    known = True
    pct = ZERO
    if rail.fee_pct is None:
        known = False
    else:
        pct = rail.fee_pct
    fixed = ZERO
    if rail.fee_fixed is None:
        known = False
    else:
        converted = convert(rail.fee_fixed.amount, rail.fee_fixed.currency, dst_ccy, rates)
        if converted is None:
            known = False
        else:
            fixed = converted
    iof = ZERO
    # IOF: conversão de BRL por instituição brasileira (o trilho sai de um banco BR para moeda estrangeira)
    if rail.currency == "BRL" and rail.converts and src_endpoint == "br_bank":
        if rail.iof_pct is None:
            known = False
        else:
            iof = rail.iof_pct
    return pct, fixed, iof, known


def _transfer_edge(
    src: str,
    dst: str,
    src_ccy: str,
    dst_ccy: str,
    *,
    rail: Rail | None,
    src_endpoint: str | None,
    rates: dict[str, Decimal],
    kind: str,
    channel: str,
    via: str,
    unknown_minutes: int,
) -> Edge | None:
    """Aresta de transferência priceada pelo trilho. Conversão: taxa de valoração, mas o spread do trilho é
    desconhecido, então a aresta é `incomplete`. Sem taxa para converter, não há aresta."""
    if src_ccy == dst_ccy:
        rate: Decimal | None = ONE
    else:
        rate = convert(ONE, src_ccy, dst_ccy, rates)
        if rate is None or rate <= 0:
            return None
    pct, fixed, iof, known = _rail_terms(rail, dst_ccy, src_endpoint, rates)
    if src_ccy != dst_ccy:
        known = False
    return Edge(
        src,
        dst,
        kind,  # type: ignore[arg-type]
        rate,
        fee_pct=pct,
        fee_fixed=fixed,
        minutes=rail.minutes if rail is not None else unknown_minutes,
        via=via,
        confidence="estimated" if known else "incomplete",
        min_in=rail.min_amount if rail is not None else None,
        max_in=rail.max_amount if rail is not None else None,
        iof_pct=iof,
        mid_rate=ONE if src_ccy == dst_ccy else None,
        channel=channel,  # type: ignore[arg-type]
    )


def build_graph(quotes: Sequence[Quote], accounts: Sequence[Account]) -> tuple[Graph, dict[str, Decimal]]:
    edges: dict[tuple, Edge] = {}
    balances: dict[str, Decimal] = {}
    account_nodes: dict[str, str] = {}  # node -> venue
    for a in accounts:
        n = node(a.currency, account_venue(a))
        balances[n] = balances.get(n, ZERO) + (a.balance_free or ZERO)
        account_nodes[n] = account_venue(a)

    rates = valuation_rates(quotes)
    rails = {r.id: r for r in load_rails().values()}
    digital_venues: dict[str, set[str]] = {}  # venue -> currencies present
    physical_venues: dict[str, tuple[str, set[str]]] = {}  # venue -> (city, currencies)
    ladders = _tier_ladders(quotes)
    # contas digitais são lugares digitais mesmo sem cotação própria: entram para receber transferências
    for a in accounts:
        venue = account_venue(a)
        if not venue.startswith("cash:"):
            digital_venues.setdefault(venue, set()).add(a.currency)
    for q in quotes:
        if is_reference(q):
            continue
        venue = quote_venue(q)
        minutes = MINUTES_BY_MODALITY.get(q.modality, 30)
        channel = "presencial" if q.channel == "physical" else "assistida"
        ctx = q.context or {}
        dst_venue = ctx.get("bank") if ctx.get("receive") == "bank_account" and ctx.get("bank") else venue
        if q.channel == "physical" and q.city:
            physical_venues.setdefault(venue, (q.city, set()))[1].update({q.base, q.quote})
        else:
            digital_venues.setdefault(venue, set()).update({q.base, q.quote} if dst_venue == venue else {q.base})
            if dst_venue != venue:
                digital_venues.setdefault(dst_venue, set()).add(q.quote)
        via = f"{q.source_id} {q.modality}" + (f" @{q.city}" if q.city else "")
        window = _window(q, ladders)  # in q.base, the input of the buy leg
        mid = (q.buy + q.sell) / 2 if q.buy and q.sell and q.buy > 0 and q.sell > 0 else None
        if q.buy is not None and q.buy > 0:
            pct, fixed, conf = _fee_terms(q, q.base, q.quote, q.buy)
            lo, hi = window
            _best(
                edges,
                Edge(
                    node(q.base, venue),
                    node(q.quote, dst_venue),
                    "quote",
                    q.buy,
                    fee_pct=pct,
                    fee_fixed=fixed,
                    minutes=minutes,
                    via=f"{via} (compra {q.buy})",
                    confidence=conf,
                    evidence_id=q.evidence_id,
                    min_in=lo,
                    max_in=hi,
                    mid_rate=mid,
                    channel=channel,  # type: ignore[arg-type]
                ),
            )
        if q.sell is not None and q.sell > 0 and dst_venue == venue:
            rate = ONE / q.sell
            pct, fixed, conf = _fee_terms(q, q.quote, q.base, rate)
            lo, hi = _scale(window, q.sell)  # the sell leg is fed in q.quote: amount_base * sell
            _best(
                edges,
                Edge(
                    node(q.quote, venue),
                    node(q.base, venue),
                    "quote",
                    rate,
                    fee_pct=pct,
                    fee_fixed=fixed,
                    minutes=minutes,
                    via=f"{via} (venda {q.sell})",
                    confidence=conf,
                    evidence_id=q.evidence_id,
                    min_in=lo,
                    max_in=hi,
                    mid_rate=ONE / mid if mid else None,
                    channel=channel,  # type: ignore[arg-type]
                ),
            )

    # contas digitais <-> lugares digitais: transferência priceada pelo trilho (sem trilho = incomplete)
    for n, venue in account_nodes.items():
        if venue.startswith("cash:"):
            continue
        ccy = node_currency(n)
        ep_src = endpoint_of_venue(venue)
        for dv, currencies in digital_venues.items():
            if dv == venue:
                continue
            ep_dst = endpoint_of_venue(dv)
            if ccy in currencies:
                rail_out = _rail(rails, ep_src, ep_dst, ccy, converts=False)
                rail_in = _rail(rails, ep_dst, ep_src, ccy, converts=False)
                legs_digital = (
                    (n, node(ccy, dv), rail_out, ep_src, f"transferência {venue}→{dv}"),
                    (node(ccy, dv), n, rail_in, ep_dst, f"resgate {dv}→{venue}"),
                )
                for src, dst, rail_src, ep, label in legs_digital:
                    edge = _transfer_edge(
                        src,
                        dst,
                        ccy,
                        ccy,
                        rail=rail_src,
                        src_endpoint=ep,
                        rates=rates,
                        kind="transfer",
                        channel="assistida",
                        via=label,
                        unknown_minutes=TRANSFER_MINUTES_UNKNOWN,
                    )
                    if edge is not None:
                        _best(edges, edge)
            # conversão por trilho (ex.: BRL de banco brasileiro para USD na Nomad): spread desconhecido
            for rail in rails.values():
                if not rail.converts or rail.currency != ccy or rail.from_ != ep_src or rail.to != ep_dst:
                    continue
                out = rail.out_currency
                if out not in currencies:
                    continue
                edge = _transfer_edge(
                    n,
                    node(out, dv),
                    ccy,
                    out,
                    rail=rail,
                    src_endpoint=ep_src,
                    rates=rates,
                    kind="transfer",
                    channel="assistida",
                    via=f"conversão {venue}→{dv} ({rail.id})",
                    unknown_minutes=TRANSFER_MINUTES_UNKNOWN,
                )
                if edge is not None:
                    _best(edges, edge)

    # contas <-> casas de câmbio na mesma moeda: só quando há trilho (SIPAP/depósito); sem trilho não há aresta
    for n, venue in account_nodes.items():
        if venue.startswith("cash:"):
            continue
        ccy = node_currency(n)
        ep_src = endpoint_of_venue(venue)
        for pv, (_city, currencies) in physical_venues.items():
            if ccy not in currencies:
                continue
            rail_out = _rail(rails, ep_src, "exchange_house", ccy, converts=False)
            rail_in = _rail(rails, "exchange_house", ep_src, ccy, converts=False)
            if rail_out is None and rail_in is None:
                continue
            for src, dst, rail_leg, ep, label in (
                (n, node(ccy, pv), rail_out, ep_src, f"transferência {venue}→{pv}"),
                (node(ccy, pv), n, rail_in, "exchange_house", f"transferência {pv}→{venue}"),
            ):
                edge = _transfer_edge(
                    src,
                    dst,
                    ccy,
                    ccy,
                    rail=rail_leg,
                    src_endpoint=ep,
                    rates=rates,
                    kind="transfer",
                    channel="assistida",
                    via=label,
                    unknown_minutes=TRANSFER_MINUTES_UNKNOWN,
                )
                if edge is not None:
                    _best(edges, edge)

    # casas de câmbio <-> caixa na mesma cidade (balcão, presencial)
    cities = set()
    for venue, (city, currencies) in physical_venues.items():
        cities.add(city)
        for ccy in currencies:
            cash = node(ccy, f"cash:{city}")
            _best(edges, Edge(cash, node(ccy, venue), "deposit", ONE, ZERO, ZERO, 20, f"balcão {venue}", "estimated"))
            _best(edges, Edge(node(ccy, venue), cash, "withdraw", ONE, ZERO, ZERO, 0, f"balcão {venue}", "estimated"))

    # contas digitais <-> caixa (saque/depósito em ATM): trilho `->cash`; sem trilho, incomplete
    for n, venue in account_nodes.items():
        if venue.startswith("cash:"):
            continue
        ccy = node_currency(n)
        ep_src = endpoint_of_venue(venue)
        for city in CITIES:
            cash = node(ccy, f"cash:{city}")
            withdraw = _transfer_edge(
                n,
                cash,
                ccy,
                ccy,
                rail=_rail(rails, ep_src, "cash", ccy, converts=False),
                src_endpoint=ep_src,
                rates=rates,
                kind="withdraw",
                channel="presencial",
                via=f"saque ATM {venue} em {city}",
                unknown_minutes=ATM_MINUTES_UNKNOWN,
            )
            if withdraw is not None:  # mesma moeda: sempre existe (sem trilho, incomplete)
                _best(edges, withdraw)
            _best(
                edges,
                Edge(
                    cash,
                    n,
                    "deposit",
                    ONE,
                    minutes=ATM_MINUTES_UNKNOWN,
                    via=f"depósito em {venue} em {city} (não validado)",
                    confidence="incomplete",
                    channel="presencial",
                ),
            )

    # deslocamento entre cidades (presencial): uma aresta por moeda e sentido; custo null = incomplete
    for route in load_transport().values():
        pairs = [(route.from_city, route.to_city)]
        if route.symmetric:
            pairs.append((route.to_city, route.from_city))
        for a, b in pairs:
            for ccy in CURRENCIES:
                transport = ZERO
                known = route.cost is not None
                if route.cost is not None:
                    converted = convert(route.cost.amount, route.cost.currency, ccy, rates)
                    if converted is None:
                        known = False
                    else:
                        transport = converted
                _best(
                    edges,
                    Edge(
                        node(ccy, f"cash:{a}"),
                        node(ccy, f"cash:{b}"),
                        "travel",
                        ONE,
                        minutes=route.minutes,
                        via=f"deslocamento {a}→{b} ({route.mode})",
                        confidence="estimated" if known else "incomplete",
                        transport_fixed=transport,
                        mid_rate=ONE,
                        channel="presencial",
                        border=route.border,
                    ),
                )

    g = Graph()
    for key in sorted(edges):
        g.add(edges[key])
    return g, balances


def enrich_cycle(cycle: Cycle, rates: dict[str, Decimal]) -> Cycle:
    """Ganho em cada moeda, custos na moeda de partida e aviso de declaração (taxas de valoração BRL)."""
    start_ccy = node_currency(cycle.start)
    gain_by_currency = {c: convert(cycle.gain, start_ccy, c, rates) for c in CURRENCIES}

    costs: dict[str, Decimal | None] = {}
    for key in ("spread", "fees", "iof", "transport"):
        total: Decimal | None = ZERO
        for leg in cycle.legs:
            value = getattr(leg.costs, key)
            converted = convert(value, node_currency(leg.src), start_ccy, rates)
            if value is None or converted is None or total is None:
                total = None
            else:
                total += converted
        costs[key] = total

    requires = False
    if any(leg.border for leg in cycle.legs):
        in_usd = convert(cycle.amount_in, start_ccy, "USD", rates)
        requires = in_usd is None or in_usd > DECLARATION_LIMIT_USD
    return replace(cycle, gain_by_currency=gain_by_currency, costs=costs, requires_declaration=requires)


def find_cycles_for(
    session: Session,
    *,
    data_mode: str,
    max_len: int = 4,
    min_roi: Decimal | None = None,
    start: str | None = None,
    limit: int = 200,
    lookback_s: int = 7 * 86400,
) -> list[dict[str, Any]]:
    """Cycles as contract dicts (D1), each tagged with the `data_mode` they were computed from."""
    quotes = latest_quotes(session, data_mode=data_mode, lookback_s=lookback_s)
    accounts = list(session.scalars(select(Account).where(Account.data_mode == data_mode)))
    graph, balances = build_graph(quotes, accounts)
    if start:
        balances = {k: v for k, v in balances.items() if k == start}
    rates = valuation_rates(quotes)
    return [
        {**enrich_cycle(c, rates).to_dict(), "data_mode": data_mode}
        for c in find_cycles(graph, balances, max_len=max_len, min_roi=min_roi, limit=limit)
    ]
