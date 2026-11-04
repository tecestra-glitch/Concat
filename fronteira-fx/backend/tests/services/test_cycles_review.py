"""Revisão do motor de ciclos: IOF de quem converte BRL (fonte desconhecida ou brasileira não fica zero), trilho com
IOF sempre aplicado, deslocamento verificado não some atrás de rota sem custo, e cotação de fonte descontinuada não
entra na valoração dos ciclos."""

from __future__ import annotations

from decimal import Decimal as D

import pytest

from fronteira_fx.engine.graph import node
from fronteira_fx.models import Account
from fronteira_fx.services import cycles as cyc
from fronteira_fx.services.logistics import Rail, parse_transport
from fronteira_fx.services.quotes import store_quote_draft
from tests.conftest import NOW, add_source, draft
from tests.services.test_cycles_arbitrage import account, quote


def _edge(graph, src, dst, kind=None):
    return [e for e in graph.edges if e.src == src and e.dst == dst and (kind is None or e.kind == kind)]


# --- IOF: venue fora do lado paraguaio converte BRL com IOF desconhecido -------------------------------------------


@pytest.mark.parametrize("source", ["inter", "westernunion", "demo-nomad", "demo-wu", "carteira"])
def test_brl_conversion_outside_paraguay_has_unknown_iof_never_zero(source):
    qs = [quote(source_id=source, base="BRL", quote="USD", buy=D("5.40"), sell=D("5.44"))]
    graph, _ = cyc.build_graph(qs, [])
    (buy,) = _edge(graph, node("BRL", source), node("USD", source))
    assert "iof" in buy.unknown
    assert buy.confidence == "incomplete"


def test_brl_conversion_by_a_paraguayan_house_has_no_iof():
    # casa paraguaia (cidades só no PY): IOF brasileiro não incide; a aresta segue `quoted`
    qs = [quote(source_id="chaco", base="BRL", quote="PYG", buy=D("1370"), sell=D("1390"))]
    graph, _ = cyc.build_graph(qs, [])
    (buy,) = _edge(graph, node("BRL", "chaco"), node("PYG", "chaco"))
    assert "iof" not in buy.unknown
    assert buy.confidence == "quoted"


def test_brl_conversion_at_a_foz_house_has_unknown_iof():
    qs = [quote(source_id="casa", city="FOZ", channel="physical", modality="cash", base="BRL", quote="USD",
                buy=D("5.20"), sell=D("5.30"))]
    graph, _ = cyc.build_graph(qs, [])
    (buy,) = _edge(graph, node("BRL", "casa:FOZ"), node("USD", "casa:FOZ"))
    assert "iof" in buy.unknown


# --- trilho: `iof_pct` sempre aplicado, mesmo sem conversão ----------------------------------------------------------


def _rail(**raw) -> Rail:
    base = {"id": "revolut-atm-usd", "from": "revolut", "to": "cash", "currency": "USD", "minutes": 0,
            "fee_pct": "0.02", "fee_fixed": {"amount": "0", "currency": "USD"}, "iof_pct": "0.035", "verified": False}
    base.update(raw)
    return Rail.model_validate(base)


def test_rail_iof_is_applied_on_an_atm_withdrawal_without_conversion(monkeypatch):
    monkeypatch.setattr(cyc, "load_rails", lambda: {"revolut-atm-usd": _rail()})
    accs = [account("revolut", "USD", kind="fintech", balance="1000")]
    graph, _ = cyc.build_graph([], accs)
    (wd,) = _edge(graph, node("USD", "revolut"), node("USD", "cash:CDE"), kind="withdraw")
    assert wd.iof_pct == D("0.035")
    assert wd.confidence == "estimated" and not wd.unknown
    assert wd.apply(D(1000)) == D("945")  # 1000 * (1 - 0.02 - 0.035)


def test_rail_without_iof_on_same_currency_move_stays_unknown_only_when_it_matters(monkeypatch):
    monkeypatch.setattr(cyc, "load_rails", lambda: {"revolut-atm-usd": _rail(iof_pct=None)})
    accs = [account("revolut", "USD", kind="fintech", balance="1000")]
    graph, _ = cyc.build_graph([], accs)
    (wd,) = _edge(graph, node("USD", "revolut"), node("USD", "cash:CDE"), kind="withdraw")
    assert wd.iof_pct == 0
    assert wd.confidence == "estimated"  # mesma moeda: sem IOF informado não é custo desconhecido


# --- deslocamento: rota verificada não some atrás de rota sem custo -------------------------------------------------


def test_verified_travel_route_is_not_shadowed_by_a_route_with_null_cost():
    routes = parse_transport(
        '[{"id":"foz-cde-bus","from_city":"FOZ","to_city":"CDE","mode":"bus","cost":{"amount":"6.50","currency":"BRL"},'
        '"minutes":30,"border":true,"symmetric":true,"verified":true,"source_url":"https://example.org/onibus",'
        '"checked_at":"2026-11-01"},'
        '{"id":"foz-cde-car","from_city":"FOZ","to_city":"CDE","mode":"car","cost":null,'
        '"minutes":40,"border":true,"symmetric":true,"verified":false}]'
    )
    original = cyc.load_transport
    cyc.load_transport = lambda: routes
    try:
        accs = [account("carteira", "BRL", kind="cash", location="FOZ", balance="1000")]
        graph, balances = cyc.build_graph([], accs)
    finally:
        cyc.load_transport = original
    from fronteira_fx.engine.graph import find_cycles

    cycles = find_cycles(graph, balances, max_len=2, limit=None)
    back_and_forth = [c for c in cycles if c.path == (node("BRL", "cash:FOZ"), node("BRL", "cash:CDE"), node("BRL", "cash:FOZ"))]
    assert back_and_forth, "a ida e a volta de FOZ a CDE devem ter ciclo"
    assert all(c.confidence != "incomplete" for c in back_and_forth)
    assert all(e.transport_fixed == D("6.50") for c in back_and_forth for e in c.edges)


# --- valoração: fonte descontinuada fora das taxas de conversão ----------------------------------------------------


def test_discontinued_source_quote_does_not_drive_cycle_valuation(db):
    add_source(db, "casa_a", kind="exchange_house", cities=["CDE"], branches=[("casa-a-cde", "CDE")])
    add_source(db, "casa_b", kind="exchange_house", cities=["CDE"], branches=[("casa-b-cde", "CDE")])
    add_source(db, "ueno", kind="bank", cities=[])
    for d in [
        draft("casa_a", "USD", "BRL", "5.20", "5.30", kind="executable", city="CDE", branch_id="casa-a-cde"),
        draft("casa_b", "USD", "BRL", "5.50", "5.60", kind="executable", city="CDE", branch_id="casa-b-cde"),
    ]:
        store_quote_draft(db, d, evidence_id=None, data_mode="real", captured_at=NOW)
    db.add(Account(institution="carteira", label="carteira BRL", currency="BRL", kind="cash", location="CDE",
                   balance_free=10000, balance_reserved=0, balance_in_transit=0, data_mode="real"))
    db.commit()
    before = cyc.find_cycles_for(db, data_mode="real", max_len=4, limit=None)
    store_quote_draft(
        db,
        draft("ueno", "BRL", "PYG", "1300", "1400", kind="executable", modality="account", channel="digital"),
        evidence_id=None, data_mode="real", captured_at=NOW,
    )
    db.commit()
    after = cyc.find_cycles_for(db, data_mode="real", max_len=4, limit=None)
    assert before and after
    assert after[0]["gain_by_currency"] == before[0]["gain_by_currency"]
    assert after[0]["gain_by_currency"]["PYG"] is None
