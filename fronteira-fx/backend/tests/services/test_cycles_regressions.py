"""Regressões do motor de ciclos: custo desconhecido nunca vira zero, IOF em conversões BR, ueno fora do grafo e
profundidade contada em pernas (balcão não conta)."""

from __future__ import annotations

from decimal import Decimal as D

from fronteira_fx.engine.graph import find_cycles, node
from fronteira_fx.services import cycles as cyc
from fronteira_fx.services.logistics import parse_transport
from tests.services.test_cycles_arbitrage import account, quote


def _cycle_through(cycles, *nodes):
    return [c for c in cycles if all(n in c.path for n in nodes)]


# --- M1: custo desconhecido em `costs`/`legs` ----------------------------------------------------------------------


def test_null_rail_fee_is_null_in_leg_and_cycle_costs_not_zero():
    accs = [account("nubank", "BRL", balance="5000"), account("revolut", "BRL", balance="0")]
    quotes = [quote(source_id="revolut", base="USD", quote="BRL", buy=D("5.40"), sell=D("5.44"))]
    graph, _ = cyc.build_graph(quotes, accs)
    rates = cyc.valuation_rates(quotes)
    cycles = find_cycles(graph, {node("BRL", "nubank"): D(5000)}, max_len=2, limit=500)
    rail = [c for c in cycles if c.path == (node("BRL", "nubank"), node("BRL", "revolut"), node("BRL", "nubank"))]
    assert rail, "transferência nubank -> revolut deve existir"
    d = cyc.enrich_cycle(rail[0], rates).to_dict()
    assert d["confidence"] == "incomplete"
    assert d["legs"][0]["costs"]["fees"] is None
    assert d["costs"]["fees"] is None
    assert "0" != d["legs"][0]["costs"]["fees"]


def test_conversion_with_unknown_spread_has_null_spread_not_zero():
    quotes = [quote(source_id="nomad", base="USD", quote="BRL", buy=D("5.37"), sell=D("5.42"))]
    accs = [account("brbank", "BRL", balance="5000"), account("nomad", "USD", balance="0")]
    graph, _ = cyc.build_graph(quotes, accs)
    rates = cyc.valuation_rates(quotes)
    cycles = find_cycles(graph, {node("BRL", "brbank"): D(5000)}, max_len=3, limit=500)
    conv = [c for c in cycles if node("USD", "nomad") in c.path]
    assert conv
    d = cyc.enrich_cycle(conv[0], rates).to_dict()
    assert d["confidence"] == "incomplete"
    first = d["legs"][0]
    assert first["kind"] == "transfer"
    assert first["costs"]["spread"] is None


def test_brl_to_usd_quote_at_revolut_has_unknown_iof_and_is_incomplete():
    # Revolut no Brasil converte BRL em USD: IOF de câmbio incide e a alíquota não está nos trilhos
    qs = [quote(source_id="revolut", base="USD", quote="BRL", buy=D("5.40"), sell=D("5.44"), kind="indicative")]
    accs = [account("revolut", "BRL", kind="fintech", balance="10000"), account("revolut", "USD", kind="fintech", balance="0")]
    graph, _ = cyc.build_graph(qs, accs)
    rates = cyc.valuation_rates(qs)
    cycles = find_cycles(graph, {node("BRL", "revolut"): D(10000)}, max_len=2, limit=50)
    hit = [c for c in cycles if c.path[1] == node("USD", "revolut")]
    assert hit
    d = cyc.enrich_cycle(hit[0], rates).to_dict()
    assert d["confidence"] == "incomplete"
    assert d["legs"][0]["costs"]["iof"] is None
    assert d["costs"]["iof"] is None


def test_foreign_quote_at_fox_house_has_unknown_iof():
    qs = [quote(source_id="casa", city="FOZ", channel="physical", modality="cash", buy=D("5.20"), sell=D("5.30"))]
    graph, _ = cyc.build_graph(qs, [])
    # venda de USD pela casa de FOZ: entra BRL (o IOF incide sobre o BRL que sai do Brasil)
    (sell,) = [e for e in graph.edges if e.src == node("BRL", "casa:FOZ") and e.dst == node("USD", "casa:FOZ")]
    assert "iof" in sell.unknown and sell.confidence == "incomplete"


def test_quote_outside_brazil_keeps_known_zero_iof():
    qs = [quote(source_id="chaco", city="CDE", channel="physical", modality="cash", buy=D("5.40"), sell=D("5.44"))]
    graph, _ = cyc.build_graph(qs, [])
    cycles = find_cycles(graph, {node("USD", "chaco:CDE"): D(100)}, max_len=2, limit=20)
    assert cycles
    exchange = next(leg for c in cycles for leg in c.legs if leg.kind == "exchange")
    assert exchange.costs.iof == D(0)  # não é conversão de BRL em instituição brasileira: IOF não se aplica


# --- SC-1: ueno (descontinuado) fora dos ciclos ---------------------------------------------------------------------


def test_discontinued_source_quotes_and_accounts_are_not_in_the_graph():
    quotes = [
        quote(source_id="ueno", base="USD", quote="PYG", buy=D("7395"), sell=D("7400")),
        quote(source_id="wu", base="USD", quote="PYG", buy=D("7300"), sell=D("7310"),
              context={"receive": "bank_account", "bank": "ueno"}),
    ]
    accs = [account("ueno", "PYG", kind="bank", balance="7000000"), account("nomad", "USD", balance="100")]
    graph, balances = cyc.build_graph(quotes, accs, excluded=frozenset({"ueno"}))
    assert not [n for n in graph.nodes if "ueno" in n]
    assert node("PYG", "ueno") not in balances
    assert not [e for e in graph.edges if "ueno" in e.via]


def test_default_exclusion_reads_the_adapter_registry():
    from fronteira_fx.adapters.registry import discontinued_ids

    assert "ueno" in discontinued_ids()
    quotes = [quote(source_id="ueno", base="USD", quote="PYG", buy=D("7395"), sell=D("7400"))]
    accs = [account("ueno", "PYG", balance="7000000")]
    graph, balances = cyc.build_graph(quotes, accs)
    assert not [n for n in graph.nodes if "ueno" in n]
    assert not [n for n in balances if "ueno" in n]


# --- M3: profundidade em pernas ----------------------------------------------------------------------------------


def test_two_houses_same_city_fit_in_max_len_4():
    qs = [
        quote(source_id="a", city="CDE", channel="physical", modality="cash", buy=D("5.20"), sell=D("5.30"), kind="executable"),
        quote(source_id="b", city="CDE", channel="physical", modality="cash", buy=D("5.50"), sell=D("5.60"), kind="executable"),
    ]
    accs = [account("carteira", "BRL", kind="cash", location="CDE", balance="10000")]
    graph, balances = cyc.build_graph(qs, accs)
    cycles = find_cycles(graph, balances, max_len=4, limit=50)
    profitable = [c for c in cycles if c.gain > 0 and len(c.edges) == 6]
    assert profitable, "comprar em A e vender em B na mesma cidade deve caber em max_len=4"
    assert all(sum(1 for e in c.edges if not e.counter) <= 4 for c in cycles)


def test_two_cities_route_fits_in_max_len_4(monkeypatch):
    routes = parse_transport(
        '[{"id":"foz-cde","from_city":"FOZ","to_city":"CDE","mode":"car","cost":{"amount":"50","currency":"BRL"},'
        '"minutes":40,"border":true,"symmetric":true,"verified":false}]'
    )
    monkeypatch.setattr(cyc, "load_transport", lambda: routes)
    qs = [
        quote(source_id="a", city="CDE", channel="physical", modality="cash", buy=D("5.20"), sell=D("5.30"), kind="executable"),
        quote(source_id="b", city="FOZ", channel="physical", modality="cash", buy=D("5.50"), sell=D("5.60"), kind="executable"),
    ]
    accs = [account("carteira", "BRL", kind="cash", location="FOZ", balance="10000")]
    graph, balances = cyc.build_graph(qs, accs)
    cycles = find_cycles(graph, balances, max_len=4, limit=200)
    route = [
        c
        for c in cycles
        if c.gain > 0 and node("BRL", "cash:FOZ") in c.path and node("BRL", "cash:CDE") in c.path
        and any(e.via.startswith("deslocamento") for e in c.edges)
    ]
    assert route, "levar dinheiro vivo de FOZ para CDE, trocar e voltar deve caber em max_len=4"
    assert max(len(c.edges) for c in route) >= 8


def test_every_cycle_with_an_unknown_edge_cost_has_that_category_null():
    """Propriedade (M1): se alguma aresta de um ciclo não sabe um custo, o custo do ciclo naquela categoria é None e o
    ciclo é `incomplete`. Vale para um mercado misto (cotações, trilhos com e sem valor, deslocamento sem custo)."""
    quotes = [
        quote(source_id="revolut", base="USD", quote="BRL", buy=D("5.40"), sell=D("5.44"), kind="indicative"),
        quote(source_id="nomad", base="USD", quote="BRL", buy=D("5.37"), sell=D("5.42")),
        quote(source_id="chaco", city="CDE", channel="physical", modality="cash", buy=D("5.20"), sell=D("5.30")),
        quote(source_id="casa", city="FOZ", channel="physical", modality="cash", buy=D("5.50"), sell=D("5.60")),
        quote(source_id="chaco", city="CDE", channel="physical", modality="cash", base="USD", quote="PYG", buy=D("7300"), sell=D("7320")),
    ]
    accounts = [
        account("nubank", "BRL", balance="5000"),
        account("revolut", "BRL", balance="3000"),
        account("revolut", "USD", balance="500"),
        account("nomad", "USD", balance="200"),
        account("carteira", "BRL", kind="cash", location="FOZ", balance="8000"),
    ]
    graph, balances = cyc.build_graph(quotes, accounts)
    rates = cyc.valuation_rates(quotes)
    checked = 0
    for c in find_cycles(graph, balances, max_len=4, limit=500):
        d = cyc.enrich_cycle(c, rates)
        for edge in c.edges:
            for category in edge.unknown:
                checked += 1
                assert d.costs[category] is None, (c.path, category)
        if any(e.unknown for e in c.edges):
            assert d.confidence == "incomplete"
    assert checked > 0, "o mercado de teste precisa ter custos desconhecidos para o teste fazer sentido"
