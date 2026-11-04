"""Custo desconhecido nunca vira zero (motor), balcão não conta no limite de pernas e `edges[]` reconstrói `amount_out`."""

from __future__ import annotations

from decimal import Decimal as D

import pytest

from fronteira_fx.engine.graph import Edge, Graph, find_cycles, node

ONE = D(1)


def _fold(start_amount: D, edges: list[dict]) -> D:
    """Reaplica as arestas publicadas no contrato, como o frontend faria."""
    x = start_amount
    for e in edges:
        x = x * (ONE - D(e["fee_pct"]) - D(e["iof_pct"])) * D(e["rate"]) - D(e["fee_fixed"]) - D(e["transport_fixed"])
    return x


def test_unknown_fee_becomes_none_in_leg_costs_and_edge_is_incomplete():
    e = Edge(
        node("BRL", "nubank"),
        node("BRL", "revolut"),
        "transfer",
        ONE,
        mid_rate=ONE,
        unknown=frozenset({"fees"}),
        confidence="estimated",
    )
    assert e.confidence == "incomplete"
    costs = e.leg_costs(D(100))
    assert costs.fees is None
    assert costs.as_dict("BRL")["fees"] is None
    assert costs.spread == 0  # mesma moeda: spread conhecido e zero


@pytest.mark.parametrize("category", ["spread", "fees", "iof", "transport"])
def test_each_unknown_category_is_none_and_never_zero(category):
    e = Edge(node("BRL", "a"), node("USD", "b"), "quote", D("0.19"), mid_rate=D("0.1875"), unknown=frozenset({category}))
    costs = e.leg_costs(D(100))
    assert getattr(costs, category) is None
    for other in {"spread", "fees", "iof", "transport"} - {category}:
        assert getattr(costs, other) is not None


def test_known_costs_keep_their_numbers():
    e = Edge(
        node("USD", "a"),
        node("USD", "b"),
        "transfer",
        ONE,
        fee_pct=D("0.01"),
        fee_fixed=D("2"),
        iof_pct=D("0.0"),
        mid_rate=ONE,
        confidence="estimated",
    )
    assert e.confidence == "estimated"
    costs = e.leg_costs(D(100))
    assert costs.fees == D("3")
    assert costs.iof == D("0")
    assert costs.transport == D("0")


def test_unknown_category_must_be_a_cost_key():
    with pytest.raises(ValueError):
        Edge(node("USD", "a"), node("USD", "b"), "transfer", ONE, unknown=frozenset({"lucro"}))


def test_to_dict_publishes_iof_transport_border_ref_and_unknown_costs():
    e = Edge(
        node("BRL", "cash:FOZ"),
        node("BRL", "cash:CDE"),
        "travel",
        ONE,
        minutes=40,
        transport_fixed=D("50"),
        mid_rate=ONE,
        border=True,
        confidence="estimated",
    )
    d = e.to_dict()
    assert d["transport_fixed"] == "50"
    assert d["iof_pct"] == "0"
    assert d["border"] is True
    assert d["ref_rate"] == "1"
    assert d["unknown_costs"] == []
    unknown = Edge(node("BRL", "x"), node("USD", "y"), "quote", D("0.2"), unknown=frozenset({"iof", "spread"}))
    assert unknown.to_dict()["unknown_costs"] == ["spread", "iof"]


def test_publishing_edges_reconstructs_amount_out_with_transport_and_iof():
    g = Graph()
    g.add(  # ida: deslocamento de 50 BRL por perna (custo na moeda de saída)
        Edge(node("BRL", "cash:FOZ"), node("BRL", "cash:CDE"), "travel", ONE, minutes=40, transport_fixed=D("50"),
             mid_rate=ONE, border=True, confidence="estimated")
    )
    g.add(
        Edge(node("BRL", "cash:CDE"), node("BRL", "cash:FOZ"), "travel", ONE, minutes=40, transport_fixed=D("50"),
             mid_rate=ONE, border=True, confidence="estimated")
    )
    g.add(
        Edge(node("BRL", "nubank"), node("BRL", "revolut"), "transfer", ONE, iof_pct=D("0.0038"), mid_rate=ONE,
             confidence="estimated")
    )
    g.add(
        Edge(node("BRL", "revolut"), node("BRL", "nubank"), "transfer", ONE, mid_rate=ONE, confidence="estimated")
    )
    # fecha o ciclo FOZ -> CDE -> FOZ (duas pernas de deslocamento)
    cycles = [c for c in find_cycles(g, {node("BRL", "cash:FOZ"): D(10000)}, max_len=2, limit=10)]
    assert cycles
    c = cycles[0]
    published = [e.to_dict() for e in c.edges]
    assert _fold(c.amount_in, published) == c.amount_out


def test_counter_edges_do_not_count_toward_max_len():
    """Comprar dólar numa casa e vender noutra da mesma cidade: 6 arestas, 2 pernas de câmbio."""
    cash = node("BRL", "cash:CDE")
    g = Graph()
    edges = [
        Edge(cash, node("BRL", "a:CDE"), "deposit", ONE, minutes=20, via="balcão a", counter=True, mid_rate=ONE),
        Edge(node("BRL", "a:CDE"), node("USD", "a:CDE"), "quote", D(1) / D("5.30"), minutes=15, via="a compra",
             mid_rate=D(1) / D("5.25"), confidence="quoted"),
        Edge(node("USD", "a:CDE"), node("USD", "cash:CDE"), "withdraw", ONE, minutes=0, via="balcão a", counter=True,
             mid_rate=ONE),
        Edge(node("USD", "cash:CDE"), node("USD", "b:CDE"), "deposit", ONE, minutes=20, via="balcão b", counter=True,
             mid_rate=ONE),
        Edge(node("USD", "b:CDE"), node("BRL", "b:CDE"), "quote", D("5.50"), minutes=15, via="b venda",
             mid_rate=D("5.55"), confidence="quoted"),
        Edge(node("BRL", "b:CDE"), cash, "withdraw", ONE, minutes=0, via="balcão b", counter=True, mid_rate=ONE),
    ]
    g.extend(edges)
    cycles = find_cycles(g, {cash: D(10000)}, max_len=2, limit=10)
    assert any(len(c.edges) == 6 and c.gain > 0 for c in cycles)
    # o limite continua valendo para pernas: três trocas não cabem em 2
    assert not any(sum(1 for e in c.edges if not e.counter) > 2 for c in cycles)


def test_depth_still_limits_legs_when_counter_edges_are_free():
    cash = node("BRL", "cash:CDE")
    g = Graph()
    hops = ["a", "b", "c"]
    prev = cash
    for h in hops:
        g.add(Edge(prev, node("BRL", f"{h}:CDE"), "deposit", ONE, counter=True, mid_rate=ONE))
        g.add(Edge(node("BRL", f"{h}:CDE"), node("USD", f"{h}:CDE"), "quote", D("0.18"), mid_rate=D("0.18"),
                   confidence="quoted"))
        g.add(Edge(node("USD", f"{h}:CDE"), node("USD", "cash:CDE"), "withdraw", ONE, counter=True, mid_rate=ONE))
        prev = node("USD", "cash:CDE")
    # um ciclo de 3 trocas (3 pernas) não entra com max_len=2
    cycles = find_cycles(g, {cash: D(1000)}, max_len=2, limit=10)
    assert all(sum(1 for e in c.edges if not e.counter) <= 2 for c in cycles)
