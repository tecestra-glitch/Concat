"""WU com retirada em loja (desde 04/11/2026 a conta bancária no Paraguai está suspensa): o envio é pelo app, mas o
dinheiro só sai numa agência. A perna é presencial e fica fora do modo "pelo celular"; com conta bancária, entra."""

from __future__ import annotations

from decimal import Decimal as D

from fronteira_fx.engine.graph import celular_graph, is_celular_edge
from fronteira_fx.services import cycles as cyc
from fronteira_fx.services.quotes import latest_quotes, store_quote_draft
from tests.conftest import NOW, add_source, draft


def _wu(receive: str, channel: str):
    return draft(
        "westernunion", "BRL", "PYG", "1092.3682", None,
        modality="transfer" if receive == "bank_account" else "cash", kind="indicative", channel=channel,
        amount_base=5000, context={"payment": "pix", "receive": receive}, fees=[("tarifa", D("0"), "BRL")],
    )


def _wu_edges(db) -> list:
    graph, _ = cyc.build_graph(latest_quotes(db, data_mode="real", lookback_s=10**8), [])
    return [e for e in graph.edges if e.via.startswith("westernunion")]


def test_retirada_em_loja_e_presencial_e_sai_do_modo_celular(db):
    add_source(db, "westernunion", method="browser", kind="remittance", cities=[])
    store_quote_draft(db, _wu("cash_pickup", "physical"), evidence_id=None, data_mode="real", captured_at=NOW)
    db.commit()
    edges = _wu_edges(db)
    assert edges and all(e.channel == "presencial" for e in edges)
    assert not any(is_celular_edge(e) for e in edges)
    graph, _ = cyc.build_graph(latest_quotes(db, data_mode="real", lookback_s=10**8), [])
    assert not [e for e in celular_graph(graph).edges if e.via.startswith("westernunion")]


def test_conta_bancaria_segue_pelo_celular(db):
    add_source(db, "westernunion", method="browser", kind="remittance", cities=[])
    store_quote_draft(db, _wu("bank_account", "digital"), evidence_id=None, data_mode="real", captured_at=NOW)
    db.commit()
    edges = _wu_edges(db)
    assert edges and all(is_celular_edge(e) for e in edges)
