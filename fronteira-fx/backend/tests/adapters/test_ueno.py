from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal

from fronteira_fx.adapters import ueno
from fronteira_fx.adapters.base import AdapterStatus

from .conftest import load

URL = ueno.URL


def _card(quotes, subtitle):
    return next(q for q in quotes if q.context == {"ueno_card": subtitle})


def test_parse_html_cards(captured_at: datetime) -> None:
    res = ueno.adapter.parse(load("ueno.html"), captured_at=captured_at, url=URL)
    assert res.status == AdapterStatus.OK, res.message
    assert len(res.quotes) == 2  # USD app + USD cash; EUR cards ignored; BRL not published
    app = _card(res.quotes, "en tu app")
    cash = _card(res.quotes, "en efectivo")
    assert (app.buy, app.sell) == (Decimal("5720"), Decimal("6050"))
    assert app.modality == "account" and app.channel == "digital" and app.city is None
    assert (cash.buy, cash.sell) == (Decimal("5700"), Decimal("6060"))
    assert cash.modality == "cash" and cash.channel == "physical"
    assert all(q.base == "USD" and q.quote == "PYG" and q.unit_note == "PYG por 1 USD" for q in res.quotes)
    assert "BRL not published" in (res.message or "")  # a note, not a degradation
    assert res.evidence is not None and res.evidence.kind == "html"


def test_parse_ajax_json(captured_at: datetime) -> None:
    res = ueno.adapter.parse(load("ueno_ajax.json"), captured_at=captured_at, url=ueno.AJAX_URL)
    assert res.status == AdapterStatus.OK, res.message
    app = _card(res.quotes, "en tu app")
    assert (app.buy, app.sell) == (Decimal("5720"), Decimal("6050"))
    assert app.declared_updated_at == datetime.fromtimestamp(1793583512, tz=UTC)
    assert res.evidence is not None and res.evidence.kind == "json"


def test_nonce_extraction() -> None:
    assert ueno.nonce_from_html(load("ueno.html")) == "a987e762ac"
    assert ueno.nonce_from_html("<html></html>") is None


def test_stale(much_later: datetime) -> None:
    res = ueno.adapter.parse(load("ueno_ajax.json"), captured_at=much_later, url=ueno.AJAX_URL)
    assert res.status == AdapterStatus.STALE


def test_layout_change(captured_at: datetime) -> None:
    assert ueno.adapter.parse("", captured_at=captured_at, url=URL).status == AdapterStatus.ERROR
    no_cards = load("ueno.html").replace("divisas-card", "other-card")
    res = ueno.adapter.parse(no_cards, captured_at=captured_at, url=URL)
    assert res.status == AdapterStatus.ERROR and res.quotes == [] and "divisas-card" in (res.message or "")
    bad = json.dumps({"success": True, "data": {"cards": []}})
    assert ueno.adapter.parse(bad, captured_at=captured_at, url=ueno.AJAX_URL).status == AdapterStatus.ERROR
    zeros = json.loads(load("ueno_ajax.json"))
    for c in zeros["data"]["cards"]:
        c["compra"] = c["venta"] = 0
    assert (
        ueno.adapter.parse(json.dumps(zeros), captured_at=captured_at, url=ueno.AJAX_URL).status == AdapterStatus.ERROR
    )


def test_unknown_modality_is_degraded(captured_at: datetime) -> None:
    data = json.loads(load("ueno_ajax.json"))
    data["data"]["cards"][0]["subtitle"] = "en la luna"
    res = ueno.adapter.parse(json.dumps(data), captured_at=captured_at, url=ueno.AJAX_URL)
    assert res.status == AdapterStatus.DEGRADED and "unknown modality" in (res.message or "")
