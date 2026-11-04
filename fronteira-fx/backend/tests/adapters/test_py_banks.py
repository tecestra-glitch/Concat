"""Paraguayan bank adapters: Banco Basa, Banco Familiar (offline, fixtures captured 2026-11-04).

Banco GNB has no adapter: its Aviso Legal forbids copying the web contents without written consent (docs/adapters.md).

Convention (docs/adapters.md): buy = PYG the bank PAYS per 1 unit of the base currency,
sell = PYG the bank CHARGES. Every value below is copied from the fixture captures.
"""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest
import respx

from fronteira_fx.adapters import basa, familiar
from fronteira_fx.adapters._http import sha256_hex
from fronteira_fx.adapters.base import AdapterStatus

from .conftest import load

CAPTURED_AT = datetime(2026, 11, 4, 6, 0, tzinfo=UTC)
MUCH_LATER = datetime(2026, 12, 20, 12, 0, tzinfo=UTC)


def _find(res, source_id: str, base: str, quote: str = "PYG"):
    return next(q for q in res.quotes if q.source_id == source_id and q.base == base and q.quote == quote)


# ================================================================== Banco Basa
BASA_HTML = "basa.html"


def test_basa_parse_exact_values() -> None:
    res = basa.adapter.parse(load(BASA_HTML), captured_at=CAPTURED_AT, url=basa.URL)
    assert res.status == AdapterStatus.OK, res.message
    usd = _find(res, "basa", "USD")
    assert usd.buy == Decimal("5880") and usd.sell == Decimal("6250")
    assert usd.unit_note == "PYG por 1 USD"
    assert usd.channel == "digital" and usd.city is None and usd.kind == "indicative"
    assert usd.modality == "account" and usd.declared_updated_at is None
    brl = _find(res, "basa", "BRL")
    assert brl.buy == Decimal("1050") and brl.sell == Decimal("1180")
    assert brl.unit_note == "PYG por 1 BRL"
    # EUR and ARS are not in the supported currency set: not emitted
    assert sorted((q.base, q.quote) for q in res.quotes) == [("BRL", "PYG"), ("USD", "PYG")]


def test_basa_buy_is_below_sell() -> None:
    res = basa.adapter.parse(load(BASA_HTML), captured_at=CAPTURED_AT, url=basa.URL)
    assert all(q.buy <= q.sell for q in res.quotes)


def test_basa_inverted_labels_are_degraded() -> None:
    html = load(BASA_HTML).replace("Compra 5.880 | Venta 6.250", "Compra 6.250 | Venta 5.880")
    res = basa.adapter.parse(html, captured_at=CAPTURED_AT, url=basa.URL)
    assert res.status == AdapterStatus.DEGRADED and "invert" in (res.message or "").lower()


def test_basa_layout_change_is_error() -> None:
    html = load(BASA_HTML).replace("cotizacion/dolar.png", "x/dolar_v2.png").replace("Compra", "Buy")
    res = basa.adapter.parse(html, captured_at=CAPTURED_AT, url=basa.URL)
    assert res.status == AdapterStatus.ERROR and res.quotes == []


def test_basa_missing_brl_is_degraded() -> None:
    html = load(BASA_HTML).replace("cotizacion/reales.png", "cotizacion/otra.png")
    res = basa.adapter.parse(html, captured_at=CAPTURED_AT, url=basa.URL)
    assert res.status == AdapterStatus.DEGRADED and "missing BRL" in (res.message or "")
    assert [q.base for q in res.quotes] == ["USD"]


def test_basa_evidence_hash() -> None:
    html = load(BASA_HTML)
    res = basa.adapter.parse(html, captured_at=CAPTURED_AT, url=basa.URL)
    assert res.evidence is not None and res.evidence.sha256 == sha256_hex(html)
    assert "5880" in res.evidence.excerpt and "1180" in res.evidence.excerpt


@respx.mock
async def test_basa_fetch_ok() -> None:
    respx.get(basa.URL).mock(return_value=httpx.Response(200, text=load(BASA_HTML)))
    res = await basa.adapter.fetch()
    assert res.status == AdapterStatus.OK and len(res.quotes) == 2


@respx.mock
async def test_basa_fetch_403_is_blocked() -> None:
    respx.get(basa.URL).mock(return_value=httpx.Response(403, text="forbidden"))
    res = await basa.adapter.fetch()
    assert res.status == AdapterStatus.BLOCKED and res.quotes == []


@respx.mock
async def test_basa_fetch_500_is_error() -> None:
    respx.get(basa.URL).mock(return_value=httpx.Response(500, text="oops"))
    assert (await basa.adapter.fetch()).status == AdapterStatus.ERROR


# ================================================================== Banco Familiar
FAMILIAR_HTML = "familiar.html"


def test_familiar_parse_transfer_usd() -> None:
    res = familiar.adapter.parse(load(FAMILIAR_HTML), captured_at=CAPTURED_AT, url=familiar.URL)
    assert res.status == AdapterStatus.OK, res.message
    usd = _find(res, "familiar", "USD")
    assert usd.buy == Decimal("5910") and usd.sell == Decimal("6250")
    assert usd.modality == "transfer" and usd.channel == "digital" and usd.city is None
    assert usd.kind == "indicative" and usd.unit_note == "PYG por 1 USD"
    assert usd.context == {"product": "cheque_transferencia"}
    # the "Dólar Americano Efectivo" card (branch cash, no city) is not emitted
    assert [(q.base, q.quote) for q in res.quotes] == [("USD", "PYG")]


def test_familiar_real_card_without_modality_is_noted_not_emitted() -> None:
    res = familiar.adapter.parse(load(FAMILIAR_HTML), captured_at=CAPTURED_AT, url=familiar.URL)
    assert all(q.base != "BRL" for q in res.quotes)
    assert "Real" in (res.message or "")


def test_familiar_layout_change_is_error() -> None:
    html = load(FAMILIAR_HTML).replace("collection-item", "tarjeta")
    res = familiar.adapter.parse(html, captured_at=CAPTURED_AT, url=familiar.URL)
    assert res.status == AdapterStatus.ERROR and res.quotes == []


def test_familiar_missing_usd_card_is_error_or_degraded() -> None:
    html = load(FAMILIAR_HTML).replace("Dólar Americano Cheque / Transf.", "Otra moneda")
    res = familiar.adapter.parse(html, captured_at=CAPTURED_AT, url=familiar.URL)
    assert res.status == AdapterStatus.ERROR and res.quotes == []


def test_familiar_evidence_hash() -> None:
    html = load(FAMILIAR_HTML)
    res = familiar.adapter.parse(html, captured_at=CAPTURED_AT, url=familiar.URL)
    assert res.evidence is not None and res.evidence.sha256 == sha256_hex(html)


@respx.mock
async def test_familiar_fetch_ok_and_403() -> None:
    respx.get(familiar.URL).mock(return_value=httpx.Response(200, text=load(FAMILIAR_HTML)))
    assert (await familiar.adapter.fetch()).status == AdapterStatus.OK
    respx.get(familiar.URL).mock(return_value=httpx.Response(403, text="no"))
    assert (await familiar.adapter.fetch()).status == AdapterStatus.BLOCKED


@pytest.mark.parametrize("module", [basa, familiar])
def test_info_is_bank_digital(module) -> None:
    info = module.adapter.info
    assert info.kind == "bank" and info.method in ("html", "official_api")
    assert info.allowed_domains and info.url.startswith("https://")
    assert info.limitations
