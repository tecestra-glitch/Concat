from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal

from fronteira_fx.adapters import nomad
from fronteira_fx.adapters.base import AdapterStatus

from .conftest import load

URL = nomad.API_URL


def test_parse_history(captured_at: datetime) -> None:
    res = nomad.adapter.parse(load("nomad.json"), captured_at=captured_at, url=URL)
    assert res.status == AdapterStatus.OK, res.message
    assert len(res.quotes) == 1
    q = res.quotes[0]
    assert q.base == "USD" and q.quote == "BRL"
    assert q.buy == q.sell == Decimal("5.4437")  # newest entry 2026-11-02T05:33:01.004Z
    assert q.declared_updated_at == datetime(2026, 11, 2, 5, 33, 1, 4000, tzinfo=UTC)
    assert "BRL por 1 USD" in q.unit_note and "comercial" in q.unit_note
    assert q.kind == "indicative" and q.channel == "digital" and q.modality == "account" and q.city is None
    assert q.context == {"rate_type": "comercial", "surface": "calculadora_publica", "pair": "USD_BRL"}
    assert q.fees == []
    assert res.evidence is not None and res.evidence.kind == "json" and "dolar_exchange" in res.evidence.excerpt


def test_picks_newest_even_if_unordered(captured_at: datetime) -> None:
    data = json.loads(load("nomad.json"))
    data["history"].reverse()
    res = nomad.adapter.parse(json.dumps(data), captured_at=captured_at, url=URL)
    assert res.quotes[0].buy == Decimal("5.4437")


def test_stale(much_later: datetime) -> None:
    assert nomad.adapter.parse(load("nomad.json"), captured_at=much_later, url=URL).status == AdapterStatus.STALE


def test_html_and_bad_payloads(captured_at: datetime) -> None:
    html = '<html><div hidden data-nm-contexto data-par="USD_BRL" data-api="https://api.benomad.us/x"></div></html>'
    res = nomad.adapter.parse(html, captured_at=captured_at, url=nomad.PAGE_URL)
    assert res.status == AdapterStatus.ERROR and "api.benomad.us/x" in (res.message or "")
    assert nomad.api_url_from_html(html) == "https://api.benomad.us/x"
    assert nomad.adapter.parse("", captured_at=captured_at, url=URL).status == AdapterStatus.ERROR
    assert nomad.adapter.parse('{"history": []}', captured_at=captured_at, url=URL).status == AdapterStatus.ERROR
    broken = json.dumps({"history": [{"date": "2026-11-02T00:00:00Z", "rates": {"dolar_exchange": 0}}]})
    assert nomad.adapter.parse(broken, captured_at=captured_at, url=URL).status == AdapterStatus.ERROR


def test_limitations_mention_account_dependency() -> None:
    assert any("depende da conta" in s for s in nomad.adapter.info.limitations)
    assert "api.benomad.us" in nomad.adapter.info.allowed_domains
