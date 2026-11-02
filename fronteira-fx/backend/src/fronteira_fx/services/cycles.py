"""Position graph built from the latest quotes and the user's accounts (contract: `/v1/opportunities/cycles`).

Node = `<currency>@<venue>`; venue = source id (digital), `source:city` (exchange houses), account institution,
or `cash:<city>`. Edges: quotes (base->quote at `buy`, quote->base at `1/sell`), deposits/withdrawals between
accounts and digital venues, walk-ins between cash and exchange houses, ATM moves (unvalidated => incomplete).

Amount windows (B16): a quote simulated for `amount_base` is valid from that amount up to (not including) the next
tier of the same family (source, branch, city, pair, modality, channel); `min_amount`/`max_amount` in the quote
context are explicit bounds. The search drops an edge whose window does not accept the amount reaching it.
Reference rates (`kind=market_reference` or `modality=reference`) are never edges (B23).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..decimal_utils import ONE, ZERO
from ..engine.graph import Edge, Graph, find_cycles, node
from ..engine.routes import Confidence
from ..models import Account, Quote
from .quotes import is_reference, latest_quotes

MINUTES_BY_MODALITY = {"cash": 15, "transfer": 240, "account": 5, "card_debit": 0, "card_credit": 0, "card_virtual": 0}
# smallest money unit: a tier covers [amount_base, next_tier - TIER_STEP] because Edge windows are inclusive
TIER_STEP = Decimal("0.01")
PROBE_AMOUNT = Decimal(1000)

Window = tuple[Decimal | None, Decimal | None]
Family = tuple[str, str | None, str | None, str, str, str, str]


def account_venue(a: Account) -> str:
    if a.kind == "cash" or (a.location in ("CDE", "ASU", "PJC") and a.institution in ("carteira", "cash")):
        return f"cash:{a.location}"
    return a.institution


def quote_venue(q: Quote) -> str:
    return f"{q.source_id}:{q.city}" if q.channel == "physical" and q.city else q.source_id


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


def build_graph(quotes: Sequence[Quote], accounts: Sequence[Account]) -> tuple[Graph, dict[str, Decimal]]:
    edges: dict[tuple, Edge] = {}
    balances: dict[str, Decimal] = {}
    account_nodes: dict[str, str] = {}  # node -> venue
    for a in accounts:
        n = node(a.currency, account_venue(a))
        balances[n] = balances.get(n, ZERO) + (a.balance_free or ZERO)
        account_nodes[n] = account_venue(a)

    digital_venues: dict[str, set[str]] = {}  # venue -> currencies present
    physical_venues: dict[str, tuple[str, set[str]]] = {}  # venue -> (city, currencies)
    ladders = _tier_ladders(quotes)
    for q in quotes:
        if is_reference(q):
            continue
        venue = quote_venue(q)
        minutes = MINUTES_BY_MODALITY.get(q.modality, 30)
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
                ),
            )

    # accounts <-> digital venues (same currency): pix/transfer in, withdrawal out
    for n, venue in account_nodes.items():
        ccy = n.split("@", 1)[0]
        for dv, currencies in digital_venues.items():
            if dv == venue or ccy not in currencies:
                continue
            _best(
                edges,
                Edge(n, node(ccy, dv), "deposit", ONE, ZERO, ZERO, 10, f"transferência {venue}→{dv}", "estimated"),
            )
            _best(edges, Edge(node(ccy, dv), n, "withdraw", ONE, ZERO, ZERO, 60, f"resgate {dv}→{venue}", "estimated"))
    # same institution: account node is the venue node (e.g. PYG@ueno balance is the ueno venue)
    # exchange houses <-> cash in the same city
    cities = set()
    for venue, (city, currencies) in physical_venues.items():
        cities.add(city)
        for ccy in currencies:
            cash = node(ccy, f"cash:{city}")
            _best(edges, Edge(cash, node(ccy, venue), "deposit", ONE, ZERO, ZERO, 20, f"balcão {venue}", "estimated"))
            _best(edges, Edge(node(ccy, venue), cash, "withdraw", ONE, ZERO, ZERO, 0, f"balcão {venue}", "estimated"))
    # digital accounts <-> cash (ATM / cash deposit): costs not validated => incomplete
    for n, venue in account_nodes.items():
        if venue.startswith("cash:"):
            continue
        ccy = n.split("@", 1)[0]
        for city in sorted(cities):
            cash = node(ccy, f"cash:{city}")
            _best(
                edges,
                Edge(
                    n,
                    cash,
                    "withdraw",
                    ONE,
                    ZERO,
                    ZERO,
                    60,
                    f"saque ATM {venue} em {city} (tarifa não validada)",
                    "incomplete",
                ),
            )
            _best(
                edges,
                Edge(
                    cash,
                    n,
                    "deposit",
                    ONE,
                    ZERO,
                    ZERO,
                    60,
                    f"depósito em {venue} em {city} (não validado)",
                    "incomplete",
                ),
            )

    g = Graph()
    for key in sorted(edges):
        g.add(edges[key])
    return g, balances


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
    return [
        {**c.to_dict(), "data_mode": data_mode}
        for c in find_cycles(graph, balances, max_len=max_len, min_roi=min_roi, limit=limit)
    ]
