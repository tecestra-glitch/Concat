"""Trilhos digitais com custo (fase B): só o que tem fonte; custo sem fonte é null (incompleto), nunca zero."""

from __future__ import annotations

from decimal import Decimal

from fronteira_fx.engine.graph import Graph, find_cycles, node
from fronteira_fx.services.cycles import _rail, _transfer_edge
from fronteira_fx.services.logistics import load_rails

D = Decimal


def test_every_verified_rail_has_source_and_date():
    for r in load_rails().values():
        if r.verified:
            assert r.source_url, r.id
            assert r.as_of or r.checked_at, r.id


def test_western_union_itau_is_unavailable_and_never_used_in_the_graph():
    rails = load_rails()
    wu = rails["wu-pix-itau-py-brl-pyg"]
    assert wu.available is False
    assert wu.fee_fixed is None and wu.fee_pct is None  # "a partir de R$ 9,90" é mínimo: não vira valor fixo
    picked = _rail(rails, "br_bank", "py_bank", "BRL", converts=True)
    assert picked is not None and picked.id != wu.id  # o trilho indisponível é ignorado


def test_remitly_bancop_keeps_exchange_rate_null_and_fee_known():
    r = load_rails()["remitly-bancop-brl-pyg"]
    assert r.fee_fixed is not None and r.fee_fixed.amount == D("4.49")
    assert r.rate is None  # câmbio do app não publicado: incompleto


def test_global66_round_trip_loses_about_six_percent_and_stays_negative():
    rails = load_rails()
    brl, pyg = node("BRL", "global"), node("PYG", "global")
    ida = _transfer_edge(
        brl, pyg, "BRL", "PYG", rail=rails["global66-brl-pyg"], iof_on=False, rates={},
        kind="transfer", channel="assistida", via="Global66 BRL→PYG", unknown_minutes=60,
    )
    volta = _transfer_edge(
        pyg, brl, "PYG", "BRL", rail=rails["global66-pyg-brl"], iof_on=False, rates={},
        kind="transfer", channel="assistida", via="Global66 PYG→BRL", unknown_minutes=60,
    )
    assert ida is not None and volta is not None
    # taxa capturada: o spread já está nela, então não é desconhecido
    assert ida.rate == D("1082.62") and "spread" not in ida.unknown
    assert volta.rate == D("0.00092371926324") and "spread" not in volta.unknown
    graph = Graph()
    graph.add(ida)
    graph.add(volta)
    (cycle,) = [c for c in find_cycles(graph, {brl: D("5000")}, max_len=2, limit=None) if c.start == brl]
    roi = (cycle.amount_out - cycle.amount_in) / cycle.amount_in
    assert D("-0.063") < roi < D("-0.061"), roi  # ~ -6,2 %
    # custo de volta por captura (0 PYG operacional), mas o custo fixo da ida não foi capturado: incompleto
    assert cycle.confidence == "incomplete"


def test_global66_back_leg_costs_match_the_capture():
    volta = load_rails()["global66-pyg-brl"]
    assert volta.fee_pct == D("0.0315")  # ₲ 15.750 de ₲ 500.000
    assert volta.fee_fixed is not None and volta.fee_fixed.amount == D("0")  # "Costos operacionales: 0,00 PYG"
    assert volta.as_of == "2026-11-04"
