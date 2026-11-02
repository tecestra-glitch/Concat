"""Position graph built from the latest quotes and the user's accounts (contract: `/v1/opportunities/cycles`).

Node = `<currency>@<venue>`; venue = source id (digital), `source:city` (exchange houses), account institution,
or `cash:<city>`. Edges: quotes (base->quote at `buy`, quote->base at `1/sell`), deposits/withdrawals between
accounts and digital venues, walk-ins between cash and exchange houses, ATM moves (unvalidated => incomplete).
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..decimal_utils import ONE, ZERO
from ..engine.graph import Edge, Graph, find_cycles, node
from ..models import Account, Quote
from .quotes import latest_quotes

MINUTES_BY_MODALITY = {"cash": 15, "transfer": 240, "account": 5, "card_debit": 0, "card_credit": 0, "card_virtual": 0}


def account_venue(a: Account) -> str:
    if a.kind == "cash" or a.location in ("CDE", "ASU", "PJC") and a.institution in ("carteira", "cash"):
        return f"cash:{a.location}"
    return a.institution


def quote_venue(q: Quote) -> str:
    return f"{q.source_id}:{q.city}" if q.channel == "physical" and q.city else q.source_id


def _fee_terms(q: Quote, src_ccy: str, dst_ccy: str, rate: Decimal) -> tuple[Decimal, str]:
    """Return (fee_fixed in dst currency, confidence penalty)."""
    fixed = ZERO
    conf = "quoted" if q.kind == "executable" else "estimated"
    for f in q.fees or []:
        amount = f.get("amount")
        if amount is None:
            return fixed, "incomplete"
        amt = Decimal(str(amount))
        if f.get("currency") == src_ccy:
            fixed += amt * rate
        elif f.get("currency") == dst_ccy:
            fixed += amt
        else:
            return fixed, "incomplete"
    return fixed, conf


def _best(edges: dict[tuple[str, str, str], Edge], e: Edge) -> None:
    key = (e.src, e.dst, e.kind)
    cur = edges.get(key)
    if cur is None or e.apply(Decimal(1000)) > cur.apply(Decimal(1000)):
        edges[key] = e


def build_graph(quotes: Sequence[Quote], accounts: Sequence[Account]) -> tuple[Graph, dict[str, Decimal]]:
    edges: dict[tuple[str, str, str], Edge] = {}
    balances: dict[str, Decimal] = {}
    account_nodes: dict[str, str] = {}  # node -> venue
    for a in accounts:
        n = node(a.currency, account_venue(a))
        balances[n] = balances.get(n, ZERO) + (a.balance_free or ZERO)
        account_nodes[n] = account_venue(a)

    digital_venues: dict[str, set[str]] = {}  # venue -> currencies present
    physical_venues: dict[str, tuple[str, set[str]]] = {}  # venue -> (city, currencies)
    for q in quotes:
        if q.kind == "market_reference":
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
        if q.buy is not None and q.buy > 0:
            fixed, conf = _fee_terms(q, q.base, q.quote, q.buy)
            _best(
                edges,
                Edge(
                    node(q.base, venue),
                    node(q.quote, dst_venue),
                    "quote",
                    q.buy,
                    ZERO,
                    fixed,
                    minutes,
                    f"{via} (compra {q.buy})",
                    conf,
                    q.evidence_id,
                ),
            )  # type: ignore[arg-type]
        if q.sell is not None and q.sell > 0 and dst_venue == venue:
            rate = ONE / q.sell
            fixed, conf = _fee_terms(q, q.quote, q.base, rate)
            _best(
                edges,
                Edge(
                    node(q.quote, venue),
                    node(q.base, venue),
                    "quote",
                    rate,
                    ZERO,
                    fixed,
                    minutes,
                    f"{via} (venda {q.sell})",
                    conf,
                    q.evidence_id,
                ),
            )  # type: ignore[arg-type]

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
) -> list[dict[str, Any]]:
    quotes = latest_quotes(session, data_mode=data_mode)
    accounts = list(session.scalars(select(Account).where(Account.data_mode == data_mode)))
    graph, balances = build_graph(quotes, accounts)
    if start:
        balances = {k: v for k, v in balances.items() if k == start}
    return [c.to_dict() for c in find_cycles(graph, balances, max_len=max_len, min_roi=min_roi, limit=limit)]
