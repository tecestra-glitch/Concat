from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from fronteira_fx.adapters import alberdi
from fronteira_fx.adapters._http import TZ_ASUNCION
from fronteira_fx.adapters.base import AdapterStatus

from .conftest import load, without_tables

URL = alberdi.WS_URL


def _by_branch(quotes, branch_id, base):
    return next(q for q in quotes if q.branch_id == branch_id and q.base == base)


def test_parse_json_all_branches(captured_at: datetime) -> None:
    res = alberdi.adapter.parse(load("alberdi.json"), captured_at=captured_at, url=URL)
    assert res.status == AdapterStatus.OK, res.message
    assert len(res.quotes) == 8  # 4 branches x (USD, BRL); Salto del Guairá has no USD/BRL rows

    vm_usd = _by_branch(res.quotes, "alberdi-villamorra", "USD")
    assert (vm_usd.buy, vm_usd.sell) == (Decimal("5800"), Decimal("5920"))
    assert vm_usd.city == "ASU" and vm_usd.quote == "PYG" and vm_usd.unit_note == "PYG por 1 USD"
    assert vm_usd.modality == "cash" and vm_usd.channel == "physical" and vm_usd.kind == "indicative"
    vm_brl = _by_branch(res.quotes, "alberdi-villamorra", "BRL")
    assert (vm_brl.buy, vm_brl.sell) == (Decimal("1070"), Decimal("1155"))
    assert vm_brl.unit_note == "PYG por 1 BRL"

    cde_usd = _by_branch(res.quotes, "alberdi-ciudaddeleste", "USD")
    assert (cde_usd.buy, cde_usd.sell) == (Decimal("5800"), Decimal("5900")) and cde_usd.city == "CDE"
    cde_brl = _by_branch(res.quotes, "alberdi-ciudaddeleste", "BRL")
    assert (cde_brl.buy, cde_brl.sell) == (Decimal("1070"), Decimal("1120"))
    km4_brl = _by_branch(res.quotes, "alberdi-km4", "BRL")
    assert (km4_brl.buy, km4_brl.sell) == (Decimal("1070"), Decimal("1120")) and km4_brl.city == "CDE"
    enc_brl = _by_branch(res.quotes, "alberdi-encarnacion", "BRL")
    assert (enc_brl.buy, enc_brl.sell) == (Decimal("1075"), Decimal("1140")) and enc_brl.city is None

    # the "timer" row is the declared update time, local Paraguay time
    assert vm_usd.declared_updated_at == datetime(2026, 11, 2, 1, 33, 1, tzinfo=TZ_ASUNCION)
    # cross rates (USD -> BRL) and cheques never leak in
    assert all(q.quote == "PYG" and q.base in ("USD", "BRL") for q in res.quotes)
    assert res.evidence is not None and res.evidence.kind == "json" and len(res.evidence.sha256) == 64
    assert "alberdi-villamorra" in res.evidence.excerpt


def test_parse_html_fallback_single_branch(captured_at: datetime) -> None:
    res = alberdi.adapter.parse(load("alberdi.html"), captured_at=captured_at, url=alberdi.HOME_URL)
    assert res.status == AdapterStatus.DEGRADED  # only the selected branch is on the page
    assert "only the selected branch" in (res.message or "")
    assert {q.branch_id for q in res.quotes} == {"alberdi-villamorra"}
    usd = _by_branch(res.quotes, "alberdi-villamorra", "USD")
    brl = _by_branch(res.quotes, "alberdi-villamorra", "BRL")
    assert (usd.buy, usd.sell) == (Decimal("5800"), Decimal("5920"))
    assert (brl.buy, brl.sell) == (Decimal("1070"), Decimal("1155"))
    assert usd.declared_updated_at == datetime(2026, 11, 2, 1, 18, 1, tzinfo=TZ_ASUNCION)
    assert res.evidence is not None and res.evidence.kind == "html"


def test_stale_when_declared_old(much_later: datetime) -> None:
    res = alberdi.adapter.parse(load("alberdi.json"), captured_at=much_later, url=URL)
    assert res.status == AdapterStatus.STALE
    assert res.quotes and "old" in (res.message or "")


def test_empty_and_broken_payloads(captured_at: datetime) -> None:
    assert alberdi.adapter.parse("", captured_at=captured_at, url=URL).status == AdapterStatus.ERROR
    assert alberdi.adapter.parse("{}", captured_at=captured_at, url=URL).status == AdapterStatus.ERROR
    assert alberdi.adapter.parse("{not json", captured_at=captured_at, url=URL).status == AdapterStatus.ERROR
    html_no_table = without_tables(load("alberdi.html"))
    res = alberdi.adapter.parse(html_no_table, captured_at=captured_at, url=alberdi.HOME_URL)
    assert res.status == AdapterStatus.ERROR and res.quotes == [] and res.message


def test_missing_tracked_branch_is_degraded(captured_at: datetime) -> None:
    import json

    data = json.loads(load("alberdi.json"))
    del data["ciudaddeleste"]
    res = alberdi.adapter.parse(json.dumps(data), captured_at=captured_at, url=URL)
    assert res.status == AdapterStatus.DEGRADED
    assert "ciudaddeleste" in (res.message or "")


def test_info() -> None:
    info = alberdi.adapter.info
    assert info.id == "alberdi" and info.kind == "exchange_house"
    assert "www.cambiosalberdi.com" in info.allowed_domains
    assert set(info.cities) == {"ASU", "CDE"}
