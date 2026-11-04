"""Extensão PJC/ENC: filiais de Encarnación com cidade `ENC` e cruzamentos USD•BRL publicados pelas casas.

Offline: todos os números vêm das fixtures já capturadas (chaco.json, alberdi.json, norte.html).
"""
from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal

import pytest

from fronteira_fx.adapters import alberdi, chaco, norte
from fronteira_fx.adapters._common import city_from_text
from fronteira_fx.adapters.base import AdapterStatus
from fronteira_fx.notify.rules import _normalize_params

from .conftest import load


def _one(quotes, branch_id, base, quote):
    matches = [q for q in quotes if q.branch_id == branch_id and q.base == base and q.quote == quote]
    assert len(matches) == 1, [(q.branch_id, q.base, q.quote) for q in quotes]
    return matches[0]


# --------------------------------------------------------------------------- cidade ENC
def test_city_from_text_recognises_encarnacion() -> None:
    assert city_from_text("Encarnación") == "ENC"
    assert city_from_text("ENC. Mcal. Estigarribia - Zona Alta") == "ENC"
    assert city_from_text("Sucursal Super 6 - ENC") == "ENC"
    assert city_from_text("Salto del Guairá") is None  # fora das seis cidades rastreadas


def test_chaco_encarnacion_branches_get_enc_city() -> None:
    assert chaco.KNOWN_BRANCHES["23"].city == "ENC" and chaco.KNOWN_BRANCHES["23"].id == "chaco-23"
    assert chaco.KNOWN_BRANCHES["24"].city == "ENC"
    assert "ENC" in chaco.adapter.info.cities
    # branches of ENC are polled: default_branch_ids includes them now
    assert {"23", "24"} <= set(chaco.ChacoAdapter.default_branch_ids())


def test_chaco_enc_exchange_is_quoted_with_enc_city(captured_at: datetime) -> None:
    payload = {
        "branches": [],
        "exchanges": [
            {
                "updateTs": "2026-11-02T10:00:00-0300",
                "branchOfficeId": "23",
                "items": [
                    {"isoCode": "USD", "purchasePrice": 5800, "salePrice": 5900, "purchaseArbitrage": 1,
                     "saleArbitrage": 1},
                    {"isoCode": "BRL", "purchasePrice": 1070, "salePrice": 1130, "purchaseArbitrage": 5.1,
                     "saleArbitrage": 5.35, "arbitrage": 1},
                ],
            }
        ],
    }
    res = chaco.adapter.parse(json.dumps(payload), captured_at=captured_at, url="https://x")
    assert res.status == AdapterStatus.OK
    usd = _one(res.quotes, "chaco-23", "USD", "PYG")
    assert usd.city == "ENC" and usd.channel == "physical" and usd.unit_note == "PYG por 1 USD"
    cross = _one(res.quotes, "chaco-23", "USD", "BRL")
    assert cross.city == "ENC" and (cross.buy, cross.sell) == (Decimal("5.1"), Decimal("5.35"))


def test_alberdi_encarnacion_is_enc(captured_at: datetime) -> None:
    res = alberdi.adapter.parse(load("alberdi.json"), captured_at=captured_at, url=alberdi.WS_URL)
    assert _one(res.quotes, "alberdi-encarnacion", "BRL", "PYG").city == "ENC"
    assert _one(res.quotes, "alberdi-encarnacion", "USD", "PYG").city == "ENC"
    assert "ENC" in alberdi.adapter.info.cities


# --------------------------------------------------------------------------- cruzamentos USD•BRL
def test_alberdi_publishes_usd_brl_cross_per_branch(captured_at: datetime) -> None:
    res = alberdi.adapter.parse(load("alberdi.json"), captured_at=captured_at, url=alberdi.WS_URL)
    vm = _one(res.quotes, "alberdi-villamorra", "USD", "BRL")
    assert (vm.buy, vm.sell) == (Decimal("5.140"), Decimal("5.400"))
    assert vm.unit_note == "BRL por 1 USD (cruzado Dólar x Real)" and vm.city == "ASU"
    assert vm.channel == "physical" and vm.modality == "cash" and vm.kind == "indicative"
    assert vm.context == {"board": "cruzado", "pair": "USD x BRL"}
    km4 = _one(res.quotes, "alberdi-km4", "USD", "BRL")
    assert (km4.buy, km4.sell) == (Decimal("5.260"), Decimal("5.430")) and km4.city == "CDE"
    enc = _one(res.quotes, "alberdi-encarnacion", "USD", "BRL")
    assert (enc.buy, enc.sell) == (Decimal("5.180"), Decimal("5.400")) and enc.city == "ENC"


def test_alberdi_cheque_and_zero_crosses_are_not_quotes(captured_at: datetime) -> None:
    res = alberdi.adapter.parse(load("alberdi.json"), captured_at=captured_at, url=alberdi.WS_URL)
    # Salto del Guairá publica o cruzamento zerado: nenhuma cotação
    assert not [q for q in res.quotes if q.branch_id == "alberdi-saltodelguaira"]
    # cheque (USD CHE -> BRL) nunca vira cotação de balcão
    assert all(q.context is None or "cheque" not in str(q.context).lower() for q in res.quotes)
    usd_brl = [q for q in res.quotes if q.base == "USD" and q.quote == "BRL"]
    assert len(usd_brl) == 4  # villamorra, ciudaddeleste, km4, encarnacion
    assert all(q.buy is not None and q.sell is not None for q in usd_brl)


def test_chaco_publishes_usd_brl_cross_from_arbitrage_fields(captured_at: datetime) -> None:
    res = chaco.adapter.parse(load("chaco.json"), captured_at=captured_at, url=chaco.API_EXCHANGE.format(id="{id}"))
    cross = _one(res.quotes, "chaco-1", "USD", "BRL")
    assert (cross.buy, cross.sell) == (Decimal("5"), Decimal("5.4"))
    assert cross.city == "ASU" and cross.context == {"board": "arbitrage", "pair": "USD x BRL"}
    assert cross.unit_note == "BRL por 1 USD (cruzado arbitraje)"
    # o BRL por PYG continua sendo a cotação de balcão, intocada
    assert _one(res.quotes, "chaco-1", "BRL", "PYG").buy == Decimal("1100")


def test_norte_publishes_brl_usd_cross_row(captured_at: datetime) -> None:
    res = norte.adapter.parse(load("norte.html"), captured_at=captured_at, url=norte.HOME_URL)
    cross = _one(res.quotes, "norte-1", "USD", "BRL")
    assert (cross.buy, cross.sell) == (Decimal("5.22"), Decimal("5.44"))
    assert cross.city == "PJC" and cross.channel == "physical"
    assert cross.unit_note == "BRL por 1 USD (cruzado Real•Dólar)"
    # PJC continua sendo a matriz da Norte (norte-1)
    assert norte.KNOWN_BRANCHES["1"].city == "PJC"


def test_alberdi_partial_cross_is_degraded_not_silent(captured_at: datetime) -> None:
    payload = json.loads(load("alberdi.json"))
    for row in payload["encarnacion"]:
        if row.get("bcp") == "USD -> BRL":
            row["venta"] = ""  # compra publicada, venda vazia
    res = alberdi.adapter.parse(json.dumps(payload), captured_at=captured_at, url=alberdi.WS_URL)
    assert res.status == AdapterStatus.DEGRADED
    assert "cruzamento USD->BRL incompleto" in (res.message or "")
    assert not [q for q in res.quotes if q.branch_id == "alberdi-encarnacion" and (q.base, q.quote) == ("USD", "BRL")]


def test_alert_rules_accept_enc_city() -> None:
    assert _normalize_params("opportunity_new", {"channel": "physical", "city": "ENC"}, Decimal("0")) is not None
    with pytest.raises(ValueError, match="ENC"):
        _normalize_params("opportunity_new", {"channel": "physical", "city": "XYZ"}, Decimal("0"))
