"""B15/B16/B17/B23: the position graph built from quotes and accounts (`services/cycles.py`)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from fronteira_fx.engine.graph import Graph, find_cycles
from fronteira_fx.models import Account, Quote
from fronteira_fx.services.cycles import account_venue, build_graph
from fronteira_fx.services.opportunities import conversions_from_quotes
from fronteira_fx.services.quotes import latest_quotes
from tests.conftest import seed_market

D = Decimal


def quote(**overrides) -> Quote:
    """Transient Quote row (never flushed): `build_graph` is a pure function over rows."""
    base = dict(
        source_id="x",
        base="BRL",
        quote="PYG",
        buy=D("1370"),
        sell=D("1390"),
        unit_note="PYG por 1 BRL",
        modality="account",
        kind="executable",
        channel="digital",
        city=None,
        branch_id=None,
        amount_base=None,
        context=None,
        fees=None,
        data_mode="real",
    )
    base.update(overrides)
    return Quote(**base)


def edges_between(graph: Graph, src: str, dst: str):
    return [e for e in graph.edges if e.src == src and e.dst == dst]


# --- B17: account_venue precedence -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("kind", "location", "institution", "expected"),
    [
        ("cash", "CDE", "carteira", "cash:CDE"),
        ("bank", "CDE", "carteira", "cash:CDE"),  # cash wallet declared as bank in a border city
        ("bank", "CDE", "itau", "itau"),  # a real bank in a border city is still the bank
        ("fintech", "digital", "carteira", "carteira"),  # "carteira" only means cash in a border city
    ],
)
def test_account_venue(kind, location, institution, expected):
    acc = Account(institution=institution, label=institution, currency="USD", kind=kind, location=location)
    assert account_venue(acc) == expected


# --- B23: reference quotes are never executable legs ------------------------------------------------


def test_reference_quotes_never_become_edges_or_conversions():
    ref_modality = quote(source_id="bcp", base="USD", modality="reference", kind="indicative", buy=D(7325), sell=D(7325))
    ref_kind = quote(source_id="bcp", base="USD", modality="transfer", kind="market_reference", buy=D(7325), sell=D(7325))
    graph, _ = build_graph([ref_modality, ref_kind], [])
    # sem contas, o grafo só tem deslocamento entre cidades; nenhuma cotação de referência vira perna de troca
    assert [e for e in graph.edges if e.kind == "quote"] == []
    assert conversions_from_quotes([ref_modality, ref_kind]) == []


# --- B15: fees -> Edge.fee_pct / fee_fixed, `incomplete` only when the cost is unknown ----------------


def test_pct_fee_feeds_edge_fee_pct_and_is_not_incomplete():
    q = quote(fees=[{"label": "spread", "amount": None, "pct": "0.015", "currency": "BRL"}])
    graph, _ = build_graph([q], [])
    (buy,) = edges_between(graph, "BRL@x", "PYG@x")
    assert buy.fee_pct == D("0.015")
    assert buy.fee_fixed == 0
    assert buy.confidence == "quoted"


def test_fixed_fee_is_expressed_in_the_output_currency():
    q = quote(fees=[{"label": "tarifa", "amount": "9.9", "currency": "BRL"}])
    graph, _ = build_graph([q], [])
    (buy,) = edges_between(graph, "BRL@x", "PYG@x")
    assert buy.fee_fixed == D("9.9") * D("1370") and buy.fee_pct == 0 and buy.confidence == "quoted"
    (sell,) = edges_between(graph, "PYG@x", "BRL@x")
    assert sell.fee_fixed == D("9.9") and sell.confidence == "quoted"


def test_unknown_fee_amount_is_incomplete():
    q = quote(fees=[{"label": "tarifa", "amount": None, "currency": "BRL"}])
    graph, _ = build_graph([q], [])
    (buy,) = edges_between(graph, "BRL@x", "PYG@x")
    assert buy.confidence == "incomplete"


def test_zero_fee_in_a_third_currency_is_a_known_cost():
    q = quote(fees=[{"label": "tarifa", "amount": "0", "currency": "USD"}])
    graph, _ = build_graph([q], [])
    (buy,) = edges_between(graph, "BRL@x", "PYG@x")
    assert buy.confidence == "quoted" and buy.fee_fixed == 0


def test_nonzero_fee_in_a_third_currency_cannot_be_folded():
    q = quote(fees=[{"label": "tarifa", "amount": "2", "currency": "USD"}])
    graph, _ = build_graph([q], [])
    (buy,) = edges_between(graph, "BRL@x", "PYG@x")
    assert buy.confidence == "incomplete"


# --- B16: amount windows from amount_base tiers / context limits ------------------------------------


def test_generic_quote_is_unbounded():
    graph, _ = build_graph([quote()], [])
    (buy,) = edges_between(graph, "BRL@x", "PYG@x")
    assert buy.min_in is None and buy.max_in is None


def test_amount_tiers_become_half_open_windows():
    tiers = [
        quote(amount_base=D(5000), buy=D("1366.5"), sell=None),
        quote(amount_base=D(10000), buy=D("1371.2"), sell=None),
        quote(amount_base=D(25000), buy=D("1389.4"), sell=None),
    ]
    graph, _ = build_graph(tiers, [])
    by_min = {e.min_in: e for e in edges_between(graph, "BRL@x", "PYG@x")}
    assert set(by_min) == {D(5000), D(10000), D(25000)}
    low, mid, top = by_min[D(5000)], by_min[D(10000)], by_min[D(25000)]
    assert not low.accepts(D(4999)) and low.accepts(D(5000)) and low.accepts(D(9999)) and not low.accepts(D(10000))
    assert mid.accepts(D(10000)) and mid.accepts(D(24999)) and not mid.accepts(D(25000))
    assert top.accepts(D(25000)) and top.accepts(D(1_000_000)) and top.max_in is None
    assert "compra 1366.5" in low.via and "compra 1371.2" in mid.via and "compra 1389.4" in top.via


def test_context_limits_bound_the_edge():
    q = quote(context={"min_amount": "100", "max_amount": "50000"})
    graph, _ = build_graph([q], [])
    (buy,) = edges_between(graph, "BRL@x", "PYG@x")
    assert buy.accepts(D(100)) and buy.accepts(D(50000))
    assert not buy.accepts(D(99)) and not buy.accepts(D("50000.01"))


def test_search_discards_edges_outside_their_window():
    rows = [
        quote(amount_base=D(5000), buy=D("1366.5"), sell=None),
        quote(amount_base=D(10000), buy=D("1371.2"), sell=None),
        quote(buy=None, sell=D("1400")),  # generic PYG -> BRL leg closes the loop
    ]
    graph, _ = build_graph(rows, [])

    def vias(amount: str) -> list[str]:
        return [c.edges[0].via for c in find_cycles(graph, {"BRL@x": D(amount)}, max_len=2)]

    assert vias("7000") == ["x account (compra 1366.5)"]
    assert vias("12000") == ["x account (compra 1371.2)"]
    assert vias("3000") == []


def test_wu_tiers_from_the_market_keep_the_promo_tier_in_the_ladder(db):
    seed_market(db)
    quotes = latest_quotes(db, data_mode="real", lookback_s=None)
    graph, _ = build_graph(quotes, [])
    wu = {e.min_in: e for e in edges_between(graph, "BRL@wu", "PYG@ueno")}
    assert set(wu) == {D(5000), D(10000), D(25000), D(50000)}
    promo = wu[D(25000)]
    assert promo.accepts(D(30000)) and not promo.accepts(D(50000)) and "compra 1389.4" in promo.via
    assert wu[D(50000)].max_in is None
    assert all(e.confidence == "quoted" for e in wu.values())
