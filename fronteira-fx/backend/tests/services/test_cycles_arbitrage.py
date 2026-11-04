"""Fase A do motor: deslocamento entre cidades, trilhos, fronteira, custos por perna e ganho em cada moeda."""

from __future__ import annotations

from decimal import Decimal

from fronteira_fx.engine.graph import find_cycles, node
from fronteira_fx.models import Account, Quote
from fronteira_fx.services.cycles import build_graph, enrich_cycle, valuation_rates

D = Decimal


def quote(**overrides) -> Quote:
    base = dict(
        source_id="x",
        base="USD",
        quote="BRL",
        buy=D("5.40"),
        sell=D("5.44"),
        unit_note="BRL por 1 USD",
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


def account(institution: str, currency: str, *, kind: str = "bank", location: str = "digital", balance="1000") -> Account:
    return Account(
        institution=institution,
        label=f"{institution} {currency}",
        currency=currency,
        kind=kind,
        location=location,
        balance_free=D(balance),
        balance_reserved=D(0),
        balance_in_transit=D(0),
        data_mode="real",
    )


def edges_from_to(graph, src: str, dst: str):
    return [e for e in graph.edges if e.src == src and e.dst == dst]


def test_six_cities_have_cash_nodes_and_travel_edges_both_ways():
    graph, _ = build_graph([], [])
    for city in ("CDE", "ASU", "PJC", "ENC", "FOZ", "PPO"):
        assert node("BRL", f"cash:{city}") in graph.nodes
    # FOZ<->CDE é simétrica: vale nos dois sentidos, em cada moeda
    assert edges_from_to(graph, node("PYG", "cash:FOZ"), node("PYG", "cash:CDE"))
    assert edges_from_to(graph, node("PYG", "cash:CDE"), node("PYG", "cash:FOZ"))


def test_travel_without_cost_is_incomplete_and_keeps_its_minutes():
    graph, _ = build_graph([], [])
    (edge,) = edges_from_to(graph, node("USD", "cash:CDE"), node("USD", "cash:ASU"))
    assert edge.kind == "travel"
    assert edge.confidence == "incomplete"
    assert edge.minutes == 240
    assert edge.channel == "presencial"


def test_border_route_marks_its_legs():
    graph, _ = build_graph([], [])
    (edge,) = edges_from_to(graph, node("BRL", "cash:FOZ"), node("BRL", "cash:CDE"))
    assert edge.border is True
    (edge,) = edges_from_to(graph, node("BRL", "cash:CDE"), node("BRL", "cash:ASU"))
    assert edge.border is False


def test_transfer_without_rail_is_incomplete_never_zero_cost():
    quotes = [quote(source_id="nomad", base="USD", quote="PYG", buy=D("7300"), sell=D("7300"))]
    accounts = [account("banco_py", "USD")]  # sem trilho banco_py -> nomad em USD
    graph, _ = build_graph(quotes, accounts)
    (edge,) = edges_from_to(graph, node("USD", "banco_py"), node("USD", "nomad"))
    assert edge.kind == "transfer"
    assert edge.confidence == "incomplete"
    assert edge.channel == "assistida"


def test_transfer_with_rail_but_null_fee_stays_incomplete():
    # nomad -> revolut em USD existe em rails.json, mas com custos null
    accounts = [account("nomad", "USD"), account("revolut", "USD")]
    graph, _ = build_graph([], accounts)
    (edge,) = edges_from_to(graph, node("USD", "nomad"), node("USD", "revolut"))
    assert edge.confidence == "incomplete"
    assert edge.fee_fixed == 0  # o valor não entra como custo conhecido


def test_rail_with_known_fee_becomes_an_estimated_transfer(monkeypatch):
    from fronteira_fx.services import cycles
    from fronteira_fx.services.logistics import Rail, load_rails

    rails = {r.id: r for r in load_rails().values()}
    priced = Rail.model_validate(
        {
            **{k: v for k, v in rails["nomad-revolut-usd"].model_dump(by_alias=True).items()},
            "fee_fixed": {"amount": "1", "currency": "USD"},
            "fee_pct": "0.002",
            "verified": True,
            "source_url": "https://example.test/tarifa",
            "checked_at": "2026-11-01",
        }
    )
    monkeypatch.setattr(cycles, "load_rails", lambda: {**rails, priced.id: priced})
    accounts = [account("nomad", "USD"), account("revolut", "USD")]
    graph, _ = build_graph([], accounts)
    (edge,) = edges_from_to(graph, node("USD", "nomad"), node("USD", "revolut"))
    assert edge.confidence == "estimated"
    assert edge.fee_pct == D("0.002")
    assert edge.fee_fixed == D("1")


def test_brl_to_usd_conversion_by_rail_is_incomplete_because_spread_is_unknown():
    # a Nomad cota USD/BRL; o trilho br_bank -> nomad (BRL, com conversão) existe, mas o spread do trilho é desconhecido
    quotes = [quote(source_id="nomad", base="USD", quote="BRL", buy=D("5.37"), sell=D("5.42"))]
    accounts = [account("brbank", "BRL")]
    graph, _ = build_graph(quotes, accounts)
    (edge,) = edges_from_to(graph, node("BRL", "brbank"), node("USD", "nomad"))
    assert edge.kind == "transfer"
    assert edge.confidence == "incomplete"
    assert edge.iof_pct == 0  # o IOF do trilho não foi informado: incomplete, não zero
    assert edge.rate > 0


def test_legs_expose_kind_channel_and_costs_in_origin_currency():
    quotes = [quote(source_id="chaco", city="CDE", channel="physical", modality="cash", buy=D("5.40"), sell=D("5.44"))]
    graph, _ = build_graph(quotes, [])
    cycles = find_cycles(graph, {node("USD", "chaco:CDE"): D("100")}, max_len=2, limit=20)
    assert cycles, "a house cycle should exist"
    exchange = next(leg for c in cycles for leg in c.legs if leg.kind == "exchange")
    assert exchange.channel == "presencial"
    as_dict = exchange.costs.as_dict("USD")
    assert as_dict["currency"] == "USD"  # o custo sai na moeda em que a perna começou
    assert set(as_dict) == {"currency", "spread", "fees", "iof", "transport"}


def test_spread_is_measured_against_the_mid_rate():
    # ciclo partindo do próprio saldo da casa (USD -> BRL -> USD): o nó da casa é o único repetido
    quotes = [quote(source_id="chaco", city="CDE", channel="physical", modality="cash", buy=D("5.40"), sell=D("5.44"))]
    graph, _ = build_graph(quotes, [])
    cycles = find_cycles(graph, {node("USD", "chaco:CDE"): D("100")}, max_len=2, limit=50)
    exchange = [leg for c in cycles for leg in c.legs if leg.kind == "exchange"]
    assert exchange
    spread = exchange[0].costs.spread
    assert spread is not None and spread > 0  # comprar BRL a 5,40 com meio em 5,42 custa spread


def test_gain_by_currency_and_costs_need_valuation_rates():
    quotes = [
        quote(source_id="chaco", city="CDE", channel="physical", modality="cash", buy=D("5.40"), sell=D("5.44")),
        quote(source_id="chaco", city="CDE", channel="physical", modality="cash", base="USD", quote="PYG", buy=D("7300"), sell=D("7320")),
    ]
    graph, _ = build_graph(quotes, [])
    rates = valuation_rates(quotes)
    cycles = find_cycles(graph, {node("USD", "chaco:CDE"): D("1000")}, max_len=2, limit=20)
    enriched = [enrich_cycle(c, rates) for c in cycles]
    assert enriched
    c = enriched[0]
    assert set(c.gain_by_currency) == {"BRL", "PYG", "USD"}
    assert c.gain_by_currency["USD"] == c.gain
    assert c.gain_by_currency["BRL"] is not None
    assert set(c.costs) == {"spread", "fees", "iof", "transport"}


def test_cycle_without_rate_for_its_currency_gives_null_gain_in_that_currency():
    quotes = [quote(source_id="chaco", city="CDE", channel="physical", modality="cash", base="USD", quote="PYG", buy=D("7300"), sell=D("7320"))]
    graph, _ = build_graph(quotes, [])
    cycles = find_cycles(graph, {node("USD", "chaco:CDE"): D("1000")}, max_len=2, limit=20)
    rates = valuation_rates(quotes)  # BRL não aparece em nenhuma cotação com USD/PYG: só BRL = 1
    assert "PYG" not in rates
    enriched = enrich_cycle(cycles[0], rates)
    assert enriched.gain_by_currency["PYG"] is None
    assert enriched.gain_by_currency["USD"] is not None


def test_border_cycle_above_us_10k_requires_declaration_and_below_does_not():
    quotes = [quote(base="USD", quote="BRL", buy=D("5.40"), sell=D("5.44"))]
    rates = valuation_rates(quotes)
    graph, _ = build_graph(quotes, [])
    # ida e volta FOZ<->CDE: pernas de fronteira. BRL 60 000 ~ US$ 11 000 (acima de US$ 10 000)
    balances = {node("BRL", "cash:FOZ"): D("60000")}
    cycles = find_cycles(graph, balances, max_len=2, limit=10)
    big = [c for c in cycles if any(leg.border for leg in c.legs)]
    assert big, "the FOZ->CDE travel leg is a border leg"
    assert enrich_cycle(big[0], rates).requires_declaration is True

    small = find_cycles(graph, {node("BRL", "cash:FOZ"): D("5000")}, max_len=2, limit=10)
    small_border = [c for c in small if any(leg.border for leg in c.legs)]
    assert small_border
    assert enrich_cycle(small_border[0], rates).requires_declaration is False


def test_border_cycle_without_rate_to_usd_declares_by_precaution():
    graph, _ = build_graph([], [])
    balances = {node("BRL", "cash:FOZ"): D("100")}
    cycles = find_cycles(graph, balances, max_len=2, limit=10)
    border = [c for c in cycles if any(leg.border for leg in c.legs)]
    assert border
    assert enrich_cycle(border[0], {"BRL": D(1)}).requires_declaration is True
