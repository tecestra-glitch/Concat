"""Modo celular (regra do dono): o ranking principal só mostra ciclos inteiros pelo celular.

Arestas construídas à mão: determinísticas e sem depender das cotações demo.
"""

from __future__ import annotations

from decimal import Decimal

from fronteira_fx.engine.graph import Edge, Graph, celular_graph, find_cycles, is_celular_edge, node

D = Decimal


def edge(src: str, dst: str, *, channel: str, kind: str = "transfer", rate: str = "1", **kw) -> Edge:
    return Edge(src=src, dst=dst, kind=kind, rate=D(rate), channel=channel, confidence="estimated", **kw)


def presencial_loop() -> tuple[Graph, dict[str, Decimal]]:
    """USD@chaco:CDE -> PYG@chaco:CDE -> USD@chaco:CDE, tudo na casa (balcão): ganho só se a taxa fechar."""
    g = Graph()
    a, b = node("USD", "chaco:CDE"), node("PYG", "chaco:CDE")
    g.add(edge(a, b, channel="presencial", kind="quote", rate="7400", counter=True))
    g.add(edge(b, a, channel="presencial", kind="quote", rate="0.000140", counter=True))
    return g, {a: D("1000")}


def digital_loop() -> tuple[Graph, dict[str, Decimal]]:
    """BRL@brbank -> PYG@banco -> BRL@brbank pelo celular (assistida), com ganho."""
    g = Graph()
    a, b = node("BRL", "brbank"), node("PYG", "banco-demo-py")
    g.add(edge(a, b, channel="assistida", rate="1400", via="Pix -> banco"))
    g.add(edge(b, a, channel="assistida", rate="0.000720", via="banco -> Pix"))
    return g, {a: D("5000")}


def mixed_loop() -> tuple[Graph, dict[str, Decimal]]:
    """Digital na ida e depósito em espécie na volta: continua sendo um ciclo com perna presencial."""
    g = Graph()
    a, b = node("BRL", "brbank"), node("PYG", "banco-demo-py")
    g.add(edge(a, b, channel="assistida", rate="1400", via="Pix -> banco"))
    g.add(edge(b, a, channel="presencial", kind="withdraw", rate="0.000720", via="saque em espécie"))
    return g, {a: D("5000")}


def test_cycle_with_presencial_leg_stays_out_of_the_celular_ranking():
    graph, balances = presencial_loop()
    assert find_cycles(graph, balances, max_len=2, limit=None)  # o motor acha o ciclo
    assert find_cycles(celular_graph(graph), balances, max_len=2, limit=None) == []


def test_todos_mode_keeps_the_presencial_cycle():
    graph, balances = presencial_loop()
    cycles = find_cycles(graph, balances, max_len=2, limit=None)
    assert any(e.channel == "presencial" for c in cycles for e in c.edges)


def test_digital_cycle_enters_the_celular_ranking():
    graph, balances = digital_loop()
    cycles = find_cycles(celular_graph(graph), balances, max_len=2, limit=None)
    assert cycles
    assert all(e.channel == "assistida" for c in cycles for e in c.edges)


def test_mixed_cycle_with_cash_withdrawal_is_out_in_celular_mode():
    graph, balances = mixed_loop()
    assert find_cycles(graph, balances, max_len=2, limit=None)
    assert find_cycles(celular_graph(graph), balances, max_len=2, limit=None) == []


def test_deposit_and_travel_are_out_even_with_assisted_channel():
    for kind in ("deposit", "withdraw", "travel"):
        e = edge("USD@x", "USD@y", channel="assistida", kind=kind)
        assert not is_celular_edge(e), kind


def test_counter_edges_are_out_even_when_marked_assisted():
    e = edge("USD@x", "PYG@x", channel="assistida", kind="quote", counter=True)
    assert not is_celular_edge(e)


def test_automatizavel_counts_as_celular():
    assert is_celular_edge(edge("BRL@a", "PYG@b", channel="automatizavel"))
