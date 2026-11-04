"""Saldo simulado dos triângulos: sem conta cadastrada, cada nó parte do equivalente a R$ 5.000 (orçamento padrão do
site); com conta cadastrada vale o saldo real. A mesma volta vista de outro nó conta uma vez só."""

from __future__ import annotations

from decimal import Decimal

from fronteira_fx.engine.graph import Edge, Graph, find_cycles
from fronteira_fx.market import reads
from fronteira_fx.models import Account
from fronteira_fx.services import cycles as cyc
from tests.conftest import make_settings, seed_market

LOOKBACK = 10**8
NOTIONAL = Decimal("5000")


def _triangle_graph() -> Graph:
    g = Graph()
    g.extend(
        [
            Edge("BRL@a", "USD@b", "quote", Decimal("0.2"), via="x"),
            Edge("USD@b", "PYG@c", "quote", Decimal("6000"), via="y"),
            Edge("PYG@c", "BRL@a", "quote", Decimal("0.00085"), via="z"),
        ]
    )
    return g


def test_notional_balances_converte_pela_taxa_e_ignora_moeda_sem_taxa():
    g = _triangle_graph()
    rates = {"BRL": Decimal(1), "USD": Decimal("5")}  # PYG sem taxa de valoração: fica de fora, nunca chuta
    assert cyc.notional_balances(g, rates, NOTIONAL) == {"BRL@a": Decimal("5000.00"), "USD@b": Decimal("1000.00")}


def test_rotation_key_igual_para_a_mesma_volta_de_outro_ponto():
    g = _triangle_graph()
    balances = {"BRL@a": Decimal(5000), "USD@b": Decimal(1000), "PYG@c": Decimal(6_000_000)}
    found = find_cycles(g, balances, max_len=3, limit=None)
    assert len(found) == 3  # a mesma volta, uma por ponto de partida
    assert len({cyc._rotation_key(c) for c in found}) == 1


def test_sem_conta_simula_e_cada_volta_aparece_uma_vez(db):
    seed_market(db)
    db.commit()
    assert cyc.find_cycles_for(db, data_mode="real", max_len=3, lookback_s=LOOKBACK, limit=None) == []
    simulated = cyc.find_cycles_for(
        db, data_mode="real", max_len=3, lookback_s=LOOKBACK, limit=None, notional_brl=NOTIONAL
    )
    assert simulated, "sem conta, o saldo simulado precisa gerar ciclos no mercado de teste"
    keys = [tuple((e["from"], e["to"], e["via"]) for e in c["edges"]) for c in simulated]
    canon = set()
    for k in keys:
        i = k.index(min(k))
        canon.add(k[i:] + k[:i])
    assert len(canon) == len(simulated)  # nenhuma volta repetida por rotação
    rois = [Decimal(c["roi"]) for c in simulated]
    assert rois == sorted(rois, reverse=True)
    brl_starts = [c for c in simulated if c["start"].startswith("BRL@")]
    assert brl_starts and all(Decimal(c["legs"][0]["amount_in"]) == NOTIONAL for c in brl_starts)


def test_com_conta_cadastrada_o_valor_simulado_e_ignorado(db):
    seed_market(db)
    db.add(
        Account(
            institution="nomad",
            label="Nomad USD",
            currency="USD",
            kind="bank",
            location="digital",
            balance_free=Decimal(800),
            data_mode="real",
        )
    )
    db.commit()
    real = cyc.find_cycles_for(db, data_mode="real", max_len=3, lookback_s=LOOKBACK, limit=None)
    with_notional = cyc.find_cycles_for(
        db, data_mode="real", max_len=3, lookback_s=LOOKBACK, limit=None, notional_brl=NOTIONAL
    )
    assert with_notional == real
    assert {c["start"] for c in real} <= {"USD@nomad"}


def test_worker_grava_triangulos_simulados_sem_conta(db):
    seed_market(db)
    db.commit()
    settings = make_settings()
    expected = reads.triangle_cycles(db, data_mode="real", lookback_s=settings.quotes_lookback_s, mode="todos")
    plain = reads.triangle_cycles(
        db, data_mode="real", lookback_s=settings.quotes_lookback_s, mode="todos", notional_brl=None
    )
    assert plain == []  # o comportamento antigo: sem saldo, nada
    assert all(len(c["edges"]) == 3 for c in expected)
