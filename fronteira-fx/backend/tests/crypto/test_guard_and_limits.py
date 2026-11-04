import re

import httpx
import pytest

from fronteira_fx.crypto.guard import ReadOnlyClient, ReadOnlyViolation, RegionalGate
from fronteira_fx.crypto.limits import WindowLimiter, backoff_delay, parse_retry_after
from tests.crypto.helpers import FakeTime, Recorder, json_response


async def test_client_refuses_path_outside_allowlist_without_touching_network():
    rec = Recorder(lambda req: json_response({"ok": True}))
    client = ReadOnlyClient("https://ex.test", [re.compile(r"/public/ticker")], transport=rec.transport)
    with pytest.raises(ReadOnlyViolation):
        await client.get("/private/order")
    assert rec.requests == []
    await client.aclose()


async def test_client_exposes_only_get():
    client = ReadOnlyClient("https://ex.test", [re.compile(r"/x")], transport=Recorder(lambda r: json_response({})).transport)
    for verb in ("post", "put", "delete", "patch", "request", "send"):
        assert not hasattr(client, verb), verb
    await client.aclose()


async def test_client_does_not_follow_redirects():
    rec = Recorder(lambda req: httpx.Response(302, headers={"Location": "https://other.test/x"}))
    client = ReadOnlyClient("https://ex.test", [re.compile(r"/x")], transport=rec.transport)
    resp = await client.get("/x")
    assert resp.status_code == 302
    assert len(rec.requests) == 1
    await client.aclose()


def test_regional_gate_records_first_block_only():
    gate = RegionalGate()
    first = gate.block("binance", 451, "primeiro")
    gate.block("binance", 451, "segundo")
    assert gate.is_blocked("binance") == first
    assert gate.is_blocked("kraken") is None
    assert [b.venue for b in gate.snapshot()] == ["binance"]


async def test_window_limiter_waits_for_oldest_event_to_leave_window():
    t = FakeTime()
    limiter = WindowLimiter(2, 10.0, clock=t.clock, sleep=t.sleep)
    await limiter.acquire()
    await limiter.acquire()
    await limiter.acquire()  # precisa esperar a janela girar
    assert t.sleeps == [10.0]


async def test_window_limiter_weight_budget():
    t = FakeTime()
    limiter = WindowLimiter(100, 60.0, clock=t.clock, sleep=t.sleep)
    await limiter.acquire(60)
    await limiter.acquire(40)
    assert t.sleeps == []
    await limiter.acquire(5)
    assert t.sleeps == [60.0]


async def test_window_limiter_rejects_cost_above_max():
    limiter = WindowLimiter(5, 1.0, clock=lambda: 0.0, sleep=lambda s: None)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        await limiter.acquire(6)


def test_backoff_is_exponential_and_capped():
    assert [backoff_delay(n) for n in (1, 2, 3)] == [1.0, 2.0, 4.0]
    assert backoff_delay(20, cap=60.0) == 60.0
    with pytest.raises(ValueError):
        backoff_delay(0)


def test_retry_after_only_seconds():
    assert parse_retry_after("2") == 2.0
    assert parse_retry_after(" 0.5 ") == 0.5
    assert parse_retry_after("Wed, 21 Oct 2026 07:28:00 GMT") is None
    assert parse_retry_after(None) is None
