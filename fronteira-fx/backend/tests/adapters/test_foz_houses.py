"""Casas de câmbio de Foz do Iguaçu: Iguassu, Cataratas e Atlas (plataforma iCâmbio) e Scappini.

Offline only: parse tests run on fixtures captured 2026-11-03/04; fetch tests use respx so that no test
ever reaches the internet. Convention: buy = what the house pays for the base currency, sell = what it charges.
The Guarani rows of these houses are written as guaranis por R$ 1 with the labels inverted ("compra" > "venda"),
so PYG quotes map buy <- "venda" label and sell <- "compra" label.
"""
from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal

import httpx
import pytest
import respx

from fronteira_fx.adapters import icambio, registry, scappini
from fronteira_fx.adapters._http import TZ_SAO_PAULO
from fronteira_fx.adapters.base import AdapterStatus

from .conftest import CAPTURED_AT, MUCH_LATER, load, load_json

API = icambio.API_URL


def _by(res, base: str, quote: str):
    return [q for q in res.quotes if q.base == base and q.quote == quote]


def _one(res, base: str, quote: str):
    found = _by(res, base, quote)
    assert len(found) == 1, (base, quote, [(q.base, q.quote) for q in res.quotes])
    return found[0]


# ------------------------------------------------------------------ registry
def test_registry_has_foz_houses() -> None:
    for aid in ("iguassu", "cataratas", "atlas", "scappini"):
        a = registry.ADAPTERS[aid]
        assert a.info.id == aid
        assert a.info.cities == ["FOZ"]
        assert a.info.kind == "exchange_house"
        assert a.info.allowed_domains, aid
    assert registry.ADAPTERS["iguassu"].info.method == "html"
    assert registry.ADAPTERS["atlas"].info.method == "official_api"


# ------------------------------------------------------------------ Iguassu (HTML widget)
def test_iguassu_parses_usd_and_inverted_pyg() -> None:
    res = icambio.ADAPTERS["iguassu"].parse(load("iguassu_icambio.html"), captured_at=CAPTURED_AT,
                                            url="https://www.iguassucambio.com.br/")
    assert res.status == AdapterStatus.OK, res.message
    usd = _one(res, "USD", "BRL")
    assert (usd.buy, usd.sell) == (Decimal("5.05"), Decimal("5.70"))
    assert usd.unit_note == "BRL por 1 USD"
    assert usd.channel == "physical" and usd.city == "FOZ" and usd.modality == "cash"
    assert usd.branch_id == "iguassu-foz"
    assert usd.declared_updated_at == datetime(2026, 11, 3, 10, 52, tzinfo=TZ_SAO_PAULO)
    pyg = _one(res, "BRL", "PYG")
    # labels "compra G$ 1.280" / "venda G$ 1.050" are guaranis por R$ 1 with inverted labels
    assert (pyg.buy, pyg.sell) == (Decimal("1050"), Decimal("1280"))
    assert pyg.buy < pyg.sell
    assert "PYG por 1 BRL" in pyg.unit_note


def test_iguassu_ignores_usb_with_reason_and_other_currencies() -> None:
    res = icambio.ADAPTERS["iguassu"].parse(load("iguassu_icambio.html"), captured_at=CAPTURED_AT,
                                            url="https://www.iguassucambio.com.br/")
    assert {(q.base, q.quote) for q in res.quotes} == {("USD", "BRL"), ("BRL", "PYG")}
    assert res.message and "USB" in res.message and "dólar branco" in res.message.lower()


def test_iguassu_without_widget_table_is_error() -> None:
    html = load("iguassu_icambio.html").replace("icambio-table", "outro-widget")
    res = icambio.ADAPTERS["iguassu"].parse(html, captured_at=CAPTURED_AT, url="https://www.iguassucambio.com.br/")
    assert res.status == AdapterStatus.ERROR and res.quotes == []


def test_iguassu_stale_when_footer_is_old() -> None:
    res = icambio.ADAPTERS["iguassu"].parse(load("iguassu_icambio.html"), captured_at=MUCH_LATER,
                                            url="https://www.iguassucambio.com.br/")
    assert res.status == AdapterStatus.STALE
    assert len(res.quotes) == 2


# ------------------------------------------------------------------ Cataratas / Atlas (iCâmbio JSON)
def test_cataratas_json_quotes_and_inverted_guarani() -> None:
    raw = json.dumps(load_json("cataratas_cotacoes.json"))
    res = icambio.ADAPTERS["cataratas"].parse(raw, captured_at=CAPTURED_AT, url=API + "?tenant=10")
    assert res.status == AdapterStatus.OK, res.message
    usd = _one(res, "USD", "BRL")
    assert (usd.buy, usd.sell) == (Decimal("5.05"), Decimal("5.65"))
    assert usd.declared_updated_at == datetime(2026, 11, 3, 15, 36, 13, tzinfo=TZ_SAO_PAULO)
    assert usd.fees == []
    pyg = _one(res, "BRL", "PYG")
    assert (pyg.buy, pyg.sell) == (Decimal("1050"), Decimal("1250"))
    assert all(q.base != "USB" for q in res.quotes)
    assert res.message and "USB" in res.message


def test_cataratas_stale_after_72h() -> None:
    raw = json.dumps(load_json("cataratas_cotacoes.json"))
    res = icambio.ADAPTERS["cataratas"].parse(raw, captured_at=MUCH_LATER, url=API + "?tenant=10")
    assert res.status == AdapterStatus.STALE


def test_atlas_json_records_iof_as_fee_on_sell_side() -> None:
    raw = json.dumps(load_json("atlas_cotacoes.json"))
    res = icambio.ADAPTERS["atlas"].parse(raw, captured_at=CAPTURED_AT, url=API + "?tenant=9")
    assert res.status == AdapterStatus.OK, res.message
    usd = _one(res, "USD", "BRL")
    assert (usd.buy, usd.sell) == (Decimal("5.15"), Decimal("5.49"))
    assert len(usd.fees) == 1
    fee = usd.fees[0]
    # IOF de 3,5% sobre a venda: 5,49 x 0,035 = 0,19215 -> 0,1922 BRL por US$ 1
    assert fee.currency == "BRL" and fee.amount == Decimal("0.1922")
    assert "3,5" in fee.label and "IOF" in fee.label
    pyg = _one(res, "BRL", "PYG")
    assert (pyg.buy, pyg.sell) == (Decimal("1085"), Decimal("1250"))
    # IOF incide sobre o valor em BRL: 3,5% de R$ 1 = 0,0350 BRL por unidade, não em guaranis
    assert pyg.fees and pyg.fees[0].currency == "BRL" and pyg.fees[0].amount == Decimal("0.0350")
    assert usd.channel == "physical" and usd.city == "FOZ" and usd.branch_id == "atlas-foz"


def test_json_error_payloads_are_error() -> None:
    adapter = icambio.ADAPTERS["atlas"]
    assert adapter.parse(json.dumps({"success": False}), captured_at=CAPTURED_AT, url=API).status == AdapterStatus.ERROR
    assert adapter.parse(json.dumps({"success": True, "data": []}), captured_at=CAPTURED_AT,
                         url=API).status == AdapterStatus.ERROR
    assert adapter.parse("", captured_at=CAPTURED_AT, url=API).status == AdapterStatus.ERROR


def test_implausible_or_inverted_values_degrade() -> None:
    payload = {"success": True, "data": [
        {"moeda_codigo": "USD", "valor_compra": "0.5000", "valor_venda": "0.6000", "data_cotacao": "2026-11-03 10:00:00"},
        {"moeda_codigo": "GUA", "valor_compra": "1050.0000", "valor_venda": "1280.0000", "data_cotacao": "2026-11-03 10:00:00"},
    ]}
    res = icambio.ADAPTERS["cataratas"].parse(json.dumps(payload), captured_at=CAPTURED_AT, url=API)
    assert res.status == AdapterStatus.DEGRADED
    assert [(q.base, q.quote) for q in res.quotes] == [("BRL", "PYG")]  # the implausible USD row is dropped
    assert res.message and "implausible" in res.message


# ------------------------------------------------------------------ Scappini (Next.js page, table "Câmbio do dia")
def test_scappini_parses_card_table() -> None:
    res = scappini.adapter.parse(load("scappini_cambio_dia.html"), captured_at=CAPTURED_AT,
                                 url="https://scappinicambio.com.br/")
    assert res.status == AdapterStatus.OK, res.message
    usd = _one(res, "USD", "BRL")
    assert (usd.buy, usd.sell) == (Decimal("5.05"), Decimal("5.70"))
    pyg = _one(res, "BRL", "PYG")
    assert (pyg.buy, pyg.sell) == (Decimal("1040"), Decimal("1240"))
    assert usd.declared_updated_at == datetime(2026, 11, 3, 15, 40, 15, tzinfo=TZ_SAO_PAULO)
    assert usd.city == "FOZ" and usd.channel == "physical" and usd.branch_id == "scappini-foz"


def test_scappini_without_table_is_error() -> None:
    res = scappini.adapter.parse("<html><body><p>manutenção</p></body></html>", captured_at=CAPTURED_AT,
                                 url="https://scappinicambio.com.br/")
    assert res.status == AdapterStatus.ERROR


# ------------------------------------------------------------------ fetch (respx, never the real site)
@respx.mock
@pytest.mark.asyncio
async def test_iguassu_fetch_ok_and_blocked() -> None:
    route = respx.get("https://www.iguassucambio.com.br/").mock(
        return_value=httpx.Response(200, text=load("iguassu_icambio.html")))
    res = await icambio.ADAPTERS["iguassu"].fetch()
    assert route.called and res.status == AdapterStatus.OK
    respx.get("https://www.iguassucambio.com.br/").mock(return_value=httpx.Response(403, text="forbidden"))
    blocked = await icambio.ADAPTERS["iguassu"].fetch()
    assert blocked.status == AdapterStatus.BLOCKED


@respx.mock
@pytest.mark.asyncio
async def test_atlas_fetch_json_ok_and_server_error() -> None:
    route = respx.get(API, params={"tenant": "9"}).mock(
        return_value=httpx.Response(200, text=load("atlas_cotacoes.json"),
                                    headers={"content-type": "application/json"}))
    res = await icambio.ADAPTERS["atlas"].fetch()
    assert route.called and res.status == AdapterStatus.OK
    respx.get(API, params={"tenant": "9"}).mock(return_value=httpx.Response(500, text="boom"))
    err = await icambio.ADAPTERS["atlas"].fetch()
    assert err.status == AdapterStatus.ERROR


@respx.mock
@pytest.mark.asyncio
async def test_scappini_fetch_timeout_is_error() -> None:
    respx.get("https://scappinicambio.com.br/").mock(side_effect=httpx.ReadTimeout("slow"))
    res = await scappini.adapter.fetch()
    assert res.status == AdapterStatus.ERROR
