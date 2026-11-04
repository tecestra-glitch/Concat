from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

from fronteira_fx.adapters import chaco
from fronteira_fx.adapters._http import TZ_ASUNCION
from fronteira_fx.adapters.base import AdapterStatus

from .conftest import load, without_tables

URL = chaco.API_EXCHANGE.format(id="{id}")
MINUS3 = timezone(timedelta(hours=-3))


def _q(quotes, branch_id, base):
    return next(q for q in quotes if q.branch_id == branch_id and q.base == base)


def test_parse_combined_json(captured_at: datetime) -> None:
    res = chaco.adapter.parse(load("chaco.json"), captured_at=captured_at, url=URL)
    # branch 1 was last updated on 2026-10-30 13:39 -03:00, 2.5 days before captured_at -> stale, quotes kept
    assert res.status == AdapterStatus.STALE, res.message
    assert len(res.quotes) == 9  # 3 branches x (USD, BRL, cruzamento USD•BRL)

    asu_usd = _q(res.quotes, "chaco-1", "USD")
    assert (asu_usd.buy, asu_usd.sell) == (Decimal("5750"), Decimal("5900"))
    assert asu_usd.city == "ASU" and asu_usd.quote == "PYG" and asu_usd.unit_note == "PYG por 1 USD"
    assert asu_usd.declared_updated_at == datetime(2026, 10, 30, 13, 39, tzinfo=MINUS3)
    asu_brl = _q(res.quotes, "chaco-1", "BRL")
    assert (asu_brl.buy, asu_brl.sell) == (Decimal("1100"), Decimal("1180")) and asu_brl.unit_note == "PYG por 1 BRL"

    cde_usd = _q(res.quotes, "chaco-9", "USD")
    assert (cde_usd.buy, cde_usd.sell) == (Decimal("5810"), Decimal("5920")) and cde_usd.city == "CDE"
    cde_brl = _q(res.quotes, "chaco-9", "BRL")
    assert (cde_brl.buy, cde_brl.sell) == (Decimal("1065"), Decimal("1130"))
    assert cde_brl.declared_updated_at == datetime(2026, 10, 31, 12, 2, tzinfo=MINUS3)

    pjc_usd = _q(res.quotes, "chaco-28", "USD")
    assert (pjc_usd.buy, pjc_usd.sell) == (Decimal("5760"), Decimal("5950")) and pjc_usd.city == "PJC"
    pjc_brl = _q(res.quotes, "chaco-28", "BRL")
    assert (pjc_brl.buy, pjc_brl.sell) == (Decimal("1080"), Decimal("1140"))

    assert all(q.modality == "cash" and q.channel == "physical" and q.kind == "indicative" for q in res.quotes)
    assert res.evidence is not None and res.evidence.kind == "json" and "chaco-28" in res.evidence.excerpt


def test_parse_fresh_json_is_ok() -> None:
    data = json.loads(load("chaco.json"))
    # captured right after the newest declared update -> OK
    res = chaco.adapter.parse(json.dumps(data), captured_at=datetime(2026, 10, 31, 16, 0, tzinfo=UTC), url=URL)
    assert res.status == AdapterStatus.OK, res.message


def test_single_exchange_object(captured_at: datetime) -> None:
    data = json.loads(load("chaco.json"))["exchanges"][1]  # branch 9, CDE
    res = chaco.adapter.parse(json.dumps(data), captured_at=datetime(2026, 10, 31, 16, 0, tzinfo=UTC), url=URL)
    assert res.status == AdapterStatus.OK
    assert {q.branch_id for q in res.quotes} == {"chaco-9"} and {q.city for q in res.quotes} == {"CDE"}


def test_branch_city_mapping_from_api_list() -> None:
    branches = json.loads(load("chaco_branches.json"))
    mapped = {b["id"]: chaco._branch_from_api(b) for b in branches}
    assert mapped["1"].city == "ASU" and mapped["9"].city == "CDE" and mapped["28"].city == "PJC"
    assert mapped["16"].city is None  # Hernandarias is not one of the tracked cities
    assert mapped["23"].city == "ENC"  # Encarnación
    assert mapped["9"].id == "chaco-9" and mapped["9"].name.startswith("Ciudad del Este")
    assert set(chaco.ChacoAdapter.default_branch_ids()) == {
        "23",
        "24",
        "1",
        "2",
        "3",
        "30",
        "9",
        "11",
        "13",
        "32",
        "40",
        "28",
        "29",
    }


def test_parse_html_fallback(captured_at: datetime) -> None:
    res = chaco.adapter.parse(
        load("chaco.html"), captured_at=datetime(2026, 10, 30, 18, 0, tzinfo=UTC), url=chaco.HOME_URL
    )
    assert res.status == AdapterStatus.DEGRADED  # single branch only
    usd = _q(res.quotes, "chaco-1", "USD")
    brl = _q(res.quotes, "chaco-1", "BRL")
    assert (usd.buy, usd.sell) == (Decimal("5750"), Decimal("5900"))
    assert (brl.buy, brl.sell) == (Decimal("1100"), Decimal("1180"))
    assert usd.city == "ASU"
    assert usd.declared_updated_at == datetime(2026, 10, 30, 13, 39, tzinfo=TZ_ASUNCION)
    assert res.evidence is not None and res.evidence.kind == "html"


def test_layout_change_and_empty(captured_at: datetime) -> None:
    assert chaco.adapter.parse("", captured_at=captured_at, url=URL).status == AdapterStatus.ERROR
    assert chaco.adapter.parse("[]", captured_at=captured_at, url=URL).status == AdapterStatus.ERROR
    assert chaco.adapter.parse("{}", captured_at=captured_at, url=URL).status == AdapterStatus.ERROR
    only_branches = load("chaco_branches.json")
    res = chaco.adapter.parse(only_branches, captured_at=captured_at, url=URL)
    assert res.status == AdapterStatus.ERROR and "branch list" in (res.message or "")
    res = chaco.adapter.parse(without_tables(load("chaco.html")), captured_at=captured_at, url=chaco.HOME_URL)
    assert res.status == AdapterStatus.ERROR and res.quotes == []


def test_zero_prices_are_not_quotes(captured_at: datetime) -> None:
    data = json.loads(load("chaco.json"))
    for ex in data["exchanges"]:
        for item in ex["items"]:
            item["purchasePrice"] = 0
            item["salePrice"] = 0
    res = chaco.adapter.parse(json.dumps(data), captured_at=captured_at, url=URL)
    assert res.status == AdapterStatus.ERROR and res.quotes == []


def test_missing_currency_is_degraded() -> None:
    data = json.loads(load("chaco.json"))
    data["exchanges"] = [data["exchanges"][1]]
    data["exchanges"][0]["items"] = [i for i in data["exchanges"][0]["items"] if i["isoCode"] != "BRL"]
    res = chaco.adapter.parse(json.dumps(data), captured_at=datetime(2026, 10, 31, 16, 0, tzinfo=UTC), url=URL)
    assert res.status == AdapterStatus.DEGRADED and "missing BRL" in (res.message or "")


def test_stale(much_later: datetime) -> None:
    res = chaco.adapter.parse(load("chaco.json"), captured_at=much_later, url=URL)
    assert res.status == AdapterStatus.STALE and len(res.quotes) == 9


def test_info() -> None:
    assert chaco.adapter.info.id == "chaco"
    assert set(chaco.adapter.info.cities) == {"CDE", "ASU", "PJC", "ENC"}
    assert chaco.adapter.info.allowed_domains == ["www.cambioschaco.com.py"]
