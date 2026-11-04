"""Arestas paralelas (mesmo par de nós) são alternativas: a busca escolhe pelo montante que chega à aresta e nunca
prefere custo desconhecido a custo conhecido. Um caminho gera um único ciclo (o contrato de planos usa o `path`)."""

from __future__ import annotations

from decimal import Decimal as D

from fronteira_fx.engine.graph import Edge, Graph, choose_edge, find_cycles


def edge(src: str, dst: str, rate: str, via: str, **kw) -> Edge:
    return Edge(src, dst, "quote", D(rate), via=via, **kw)


def test_choice_follows_the_amount_that_reaches_the_edge():
    fixed = edge("A", "B", "5.45", "fixa", fee_fixed=D(20))  # 100 -> 525, 1000 -> 5430
    pct = edge("A", "B", "5.40", "cartao")  # 100 -> 540, 1000 -> 5400
    assert choose_edge([fixed, pct], D(100)).via == "cartao"
    assert choose_edge([fixed, pct], D(1000)).via == "fixa"


def test_known_cost_alternative_wins_over_an_unknown_cost_placeholder_that_ranks_higher():
    unknown = edge("A", "B", "5.50", "tarifa desconhecida", unknown=frozenset({"fees"}))
    known = edge("A", "B", "5.30", "tarifa conhecida")
    assert choose_edge([unknown, known], D(1000)).via == "tarifa conhecida"


def test_only_unknown_alternatives_still_return_one_incomplete_edge():
    a = edge("A", "B", "5.50", "a", unknown=frozenset({"fees"}))
    b = edge("A", "B", "5.40", "b", unknown=frozenset({"spread"}))
    chosen = choose_edge([a, b], D(1000))
    assert chosen is not None and chosen.confidence == "incomplete"


def test_no_alternative_accepts_the_amount_gives_no_edge():
    windowed = edge("A", "B", "5.4", "janela", min_in=D(5000), max_in=D(9999))
    assert choose_edge([windowed], D(100)) is None


def test_cycle_uses_the_known_cost_route_and_reports_estimated_not_incomplete():
    g = Graph()
    g.add(edge("USD@a", "BRL@a", "5.5", "desconhecida", unknown=frozenset({"fees"})))
    g.add(edge("USD@a", "BRL@a", "5.3", "conhecida"))
    g.add(edge("BRL@a", "USD@a", "0.2", "volta"))
    (cyc,) = find_cycles(g, {"USD@a": D(1000)}, max_len=2)
    assert cyc.confidence == "estimated"
    assert cyc.edges[0].via == "conhecida"
    assert cyc.gain == D(60)


def test_parallel_alternatives_still_yield_one_cycle_per_path():
    g = Graph()
    g.add(edge("USD@a", "BRL@a", "5.3", "uma"))
    g.add(edge("USD@a", "BRL@a", "5.2", "outra"))
    g.add(edge("BRL@a", "USD@a", "0.2", "volta"))
    cycles = find_cycles(g, {"USD@a": D(1000)}, max_len=2)
    assert len(cycles) == 1


def test_limit_is_applied_after_all_cycles_so_a_confirmable_one_is_not_cut_by_incomplete_ones():
    g = Graph()
    balances = {}
    for i in range(201):  # 201 ciclos incompletos com ROI alto (custo desconhecido tratado como fora do cálculo)
        usd, brl = f"USD@x{i}", f"BRL@x{i}"
        g.add(edge(usd, brl, "2", f"inc{i}", unknown=frozenset({"fees"})))
        g.add(edge(brl, usd, "0.9", f"volta{i}"))
        balances[usd] = D(1000)
    g.add(edge("USD@ok", "BRL@ok", "1.05", "confirmavel"))
    g.add(edge("BRL@ok", "USD@ok", "1", "volta-ok"))
    balances["USD@ok"] = D(1000)
    top = find_cycles(g, balances, max_len=2, limit=200)
    assert all(c.start != "USD@ok" for c in top)
    everything = find_cycles(g, balances, max_len=2, limit=None)
    confirmable = [c for c in everything if c.start == "USD@ok"]
    assert confirmable and confirmable[0].confidence == "estimated"
