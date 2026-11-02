from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest
import respx

from fronteira_fx.adapters import revolut
from fronteira_fx.adapters.base import AdapterStatus

from .conftest import load

URL = revolut.QUOTE_URL


def test_parse_single_leg_brl_to_usd(captured_at: datetime) -> None:
    res = revolut.adapter.parse(load("revolut.json"), captured_at=captured_at, url=URL)
    assert res.status == AdapterStatus.DEGRADED  # only one direction captured
    q = res.quotes[0]
    assert q.base == "USD" and q.quote == "BRL"
    # rate BRL->USD 0.1832458994861666 -> house sells USD at 1/rate BRL
    assert q.sell == Decimal("5.457148") and q.buy is None
    assert q.declared_updated_at == datetime.fromtimestamp(1793597410.256, tz=UTC)
    assert q.context == {"country": "BR", "locale": "pt-BR", "plan": "unknown", "surface": "public_quote_api"}
    assert q.kind == "indicative" and q.channel == "digital" and q.city is None
    assert res.evidence is not None and "fxTooltip" in res.evidence.excerpt


def test_parse_both_legs(captured_at: datetime) -> None:
    leg_sell = json.loads(load("revolut.json"))["quotes"][0]
    leg_buy = {
        "sender": {"amount": 1000, "currency": "USD"},
        "recipient": {"amount": 5400, "currency": "BRL"},
        "rate": {"from": "USD", "to": "BRL", "rate": 5.4012, "timestamp": 1793597410256},
    }
    payload = json.dumps({"quotes": [leg_sell, leg_buy], "request": {"country": "BR", "locale": "pt-BR"}})
    res = revolut.adapter.parse(payload, captured_at=captured_at, url=URL)
    assert res.status == AdapterStatus.OK, res.message
    q = res.quotes[0]
    assert q.buy == Decimal("5.401200") and q.sell == Decimal("5.457148")
    assert q.amount_base == Decimal("1000")


def test_blocked_and_bad_payloads(captured_at: datetime) -> None:
    html = revolut.adapter.parse("<html>Access denied</html>", captured_at=captured_at, url=URL)
    assert html.status == AdapterStatus.BLOCKED and "manually" in (html.message or "")
    assert revolut.adapter.parse("", captured_at=captured_at, url=URL).status == AdapterStatus.ERROR
    assert revolut.adapter.parse("{}", captured_at=captured_at, url=URL).status == AdapterStatus.ERROR
    assert (
        revolut.adapter.parse('{"rate": {"from": "USD", "to": "BRL"}}', captured_at=captured_at, url=URL).status
        == AdapterStatus.ERROR
    )


def test_stale(much_later: datetime) -> None:
    assert revolut.adapter.parse(load("revolut.json"), captured_at=much_later, url=URL).status == AdapterStatus.STALE


@pytest.mark.asyncio
@respx.mock
async def test_fetch_403_is_blocked() -> None:
    respx.get(url__startswith=URL).mock(return_value=httpx.Response(403, text="<html>Forbidden</html>"))
    res = await revolut.adapter.fetch()
    assert res.status == AdapterStatus.BLOCKED
    assert "403" in (res.message or "") and "manually" in (res.message or "")


@pytest.mark.asyncio
@respx.mock
async def test_fetch_two_legs() -> None:
    now_ms = int(datetime.now(tz=UTC).timestamp() * 1000)

    def responder(request: httpx.Request) -> httpx.Response:
        frm, to = request.url.params["fromCurrency"], request.url.params["toCurrency"]
        assert request.url.params["localeCode"] == "pt-BR"
        rate = 5.4 if frm == "USD" else 1 / 5.5
        body = {
            "sender": {"amount": 1000, "currency": frm},
            "recipient": {"amount": 1, "currency": to},
            "rate": {"from": frm, "to": to, "rate": rate, "timestamp": now_ms},
        }
        return httpx.Response(200, json=body)

    respx.get(url__startswith=URL).mock(side_effect=responder)
    res = await revolut.adapter.fetch()
    assert res.status == AdapterStatus.OK, res.message
    assert res.quotes[0].buy == Decimal("5.400000") and res.quotes[0].sell == Decimal("5.500000")


def test_info_limitations() -> None:
    assert any("manualmente" in s for s in revolut.adapter.info.limitations)
