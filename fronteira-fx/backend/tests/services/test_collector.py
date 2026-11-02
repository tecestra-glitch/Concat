import hashlib
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
import respx
from sqlalchemy import func, select

from fronteira_fx.adapters.base import AdapterResult, AdapterStatus, EvidenceDraft
from fronteira_fx.models import Evidence, Opportunity, Quote, QuoteEvent, Source, Task, WatchState
from fronteira_fx.services.collector import Collector, RateLimited, UnknownSource, WrongDataMode, backoff_delay
from tests.conftest import NOW, make_settings
from tests.fakes import Clock, FakeAdapter

D = Decimal
LAST_MODIFIED = "Mon, 02 Nov 2026 11:00:00 GMT"


class ConditionalAdapter(FakeAdapter):
    """An html adapter that lets the collector do the (conditional) GET and only parses the body."""

    conditional_get = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.parsed = 0

    def parse(self, raw, *, captured_at, url, **params):
        self.parsed += 1
        text = raw.decode() if isinstance(raw, bytes) else raw
        ev = EvidenceDraft(
            source_id=self.info.id,
            kind="html",
            url=url,
            captured_at=captured_at,
            sha256=hashlib.sha256(text.encode()).hexdigest(),
            excerpt=text[:200],
            rules=["parser v1"],
        )
        return AdapterResult(status=AdapterStatus.OK, quotes=self._quotes(), evidence=ev)


@pytest.fixture
def collector_env(session_factory):
    settings = make_settings()
    clock = Clock()
    adapter = FakeAdapter()
    collector = Collector(session_factory, settings, adapters={"chaco": adapter}, now_fn=clock)
    return collector, adapter, clock, session_factory


async def test_run_once_stores_quotes_evidence_events_and_health(collector_env):
    collector, adapter, clock, sf = collector_env
    outcomes = await collector.run_once()
    assert len(outcomes) == 1 and outcomes[0].quotes_stored == 1 and outcomes[0].health == "ok"
    with sf() as s:
        src = s.get(Source, "chaco")
        assert src.health == "ok" and src.consecutive_failures == 0 and src.next_poll_at == NOW + timedelta(seconds=300)
        assert src.data_mode == "real"
        assert s.scalar(select(func.count(Quote.id))) == 1
        assert s.scalar(select(func.count(Evidence.id))) == 1
        q = s.scalars(select(Quote)).one()
        assert q.evidence_id is not None and q.series_key == "chaco:CDE:USD/PYG:cash:@chaco-cde"
        types = [e.type for e in s.scalars(select(QuoteEvent).order_by(QuoteEvent.id))]
        assert "quote.updated" in types and "source.health" in types and "opportunity.updated" in types
        assert s.scalar(select(func.count(Opportunity.id))) >= 0

    # second run within the poll interval is skipped (backoff/schedule)
    outcomes = await collector.run_once()
    assert outcomes[0].skipped and adapter.calls == 1
    clock.t = NOW + timedelta(seconds=301)
    outcomes = await collector.run_once()
    assert not outcomes[0].skipped and adapter.calls == 2


async def test_stale_recapture_stores_quote_without_events(collector_env):
    collector, adapter, clock, sf = collector_env
    await collector.run_once()
    with sf() as s:
        events_before = s.scalar(select(func.count(QuoteEvent.id)))
    clock.t = NOW + timedelta(seconds=600)
    out = await collector.run_once()  # same sha256 => stale re-capture
    assert out[0].new_capture is False and out[0].quotes_stored == 1
    with sf() as s:
        assert s.scalar(select(func.count(Quote.id))) == 2
        assert s.scalar(select(func.count(Evidence.id))) == 1  # evidence reused
        assert s.scalar(select(func.count(QuoteEvent.id))) == events_before
        declared = {q.declared_updated_at for q in s.scalars(select(Quote))}
        assert len(declared) == 1  # volatility will treat it as stale input


async def test_failure_backoff_and_recovery(session_factory):
    settings = make_settings()
    clock = Clock()
    adapter = FakeAdapter(status=AdapterStatus.BLOCKED)
    collector = Collector(session_factory, settings, adapters={"chaco": adapter}, now_fn=clock)
    await collector.run_once()
    with session_factory() as s:
        src = s.get(Source, "chaco")
        assert src.health == "blocked" and src.consecutive_failures == 1 and src.last_error == "403 anti-bot"
        assert src.next_poll_at == NOW + timedelta(seconds=300)
    clock.t = NOW + timedelta(seconds=301)
    await collector.run_once()
    with session_factory() as s:
        src = s.get(Source, "chaco")
        assert src.consecutive_failures == 2 and src.next_poll_at == clock.t + timedelta(seconds=600)
    assert backoff_delay(300, 10, 3600) == timedelta(seconds=3600)
    # recovery resets the counter
    adapter.status = AdapterStatus.OK
    clock.t = clock.t + timedelta(seconds=601)
    await collector.run_once()
    with session_factory() as s:
        src = s.get(Source, "chaco")
        assert src.health == "ok" and src.consecutive_failures == 0


async def test_adapter_exception_is_contained(session_factory):
    collector = Collector(
        session_factory, make_settings(), adapters={"chaco": FakeAdapter(raise_exc=True)}, now_fn=Clock()
    )
    out = await collector.run_once()
    assert out[0].health == "degraded" and "RuntimeError" in (out[0].message or "")


async def test_request_quote_done_queued_blocked(session_factory):
    clock = Clock()
    html = FakeAdapter("chaco")
    browser = FakeAdapter("wu", method="browser")
    blocked = FakeAdapter("maxi", status=AdapterStatus.BLOCKED)
    collector = Collector(
        session_factory, make_settings(), adapters={"chaco": html, "wu": browser, "maxi": blocked}, now_fn=clock
    )
    done = await collector.request_quote("chaco", {"base": "USD", "quote": "PYG"})
    assert done["status"] == "done" and done["quote"].source_id == "chaco"
    queued = await collector.request_quote("wu", {"amount": "5000"})
    assert queued["status"] == "queued" and queued["job_id"]
    with session_factory() as s:
        assert s.get(Task, queued["job_id"]).status == "queued"
    unknown = await collector.request_quote("nope", {})
    assert unknown["status"] == "blocked"
    blk = await collector.request_quote("maxi", {})
    assert blk["status"] == "blocked" and "403" in blk["reason"]
    # worker processes the queued browser task
    n = await collector.process_tasks()
    assert n == 1
    with session_factory() as s:
        task = s.get(Task, queued["job_id"])
        assert task.status == "done" and task.result["quotes_stored"] == 1


async def test_demo_mode_never_runs_adapters(session_factory):
    adapter = FakeAdapter()
    collector = Collector(session_factory, make_settings(data_mode="demo"), adapters={"chaco": adapter}, now_fn=Clock())
    assert await collector.run_once() == []
    assert adapter.calls == 0
    res = await collector.request_quote("chaco", {})
    assert res["status"] == "blocked"


async def test_force_within_floor_returns_last_result_without_fetch(collector_env):
    """D6: a forced collection less than 60 s after the previous run never hits the provider; it returns
    the previous outcome flagged with `retry_after_s`."""
    collector, adapter, clock, sf = collector_env
    first = (await collector.run_once())[0]
    assert adapter.calls == 1
    clock.t = NOW + timedelta(seconds=30)
    out = await collector.collect(adapter, force=True)
    assert adapter.calls == 1
    assert out.skipped and out.retry_after_s == 30
    assert out.health == first.health == "ok" and out.quotes_stored == first.quotes_stored == 1
    clock.t = NOW + timedelta(seconds=61)
    out = await collector.collect(adapter, force=True)
    assert adapter.calls == 2 and not out.skipped and out.retry_after_s is None
    with sf() as s:
        assert s.scalar(select(func.count(Quote.id))) == 2


async def test_poll_now_distinguishes_unknown_mode_and_rate_limit(session_factory):
    """D4/D6: unknown adapter, wrong data mode and the 60 s floor are typed errors; no change => None."""
    clock = Clock()
    adapter = FakeAdapter()
    collector = Collector(session_factory, make_settings(), adapters={"chaco": adapter}, now_fn=clock)
    with pytest.raises(UnknownSource):
        await collector.poll_now("nope")
    first = await collector.poll_now("chaco")
    assert first is not None and first.kind == "quote_change" and adapter.calls == 1
    with pytest.raises(RateLimited) as exc:
        await collector.poll_now("chaco")
    assert exc.value.retry_after_s == 60 and adapter.calls == 1
    clock.t = NOW + timedelta(seconds=61)
    assert await collector.poll_now("chaco") is None and adapter.calls == 2  # same sha: nothing changed
    with pytest.raises(RateLimited):
        await collector.request_quote("chaco", {"base": "USD"})
    assert adapter.calls == 2
    demo = Collector(session_factory, make_settings(data_mode="demo"), adapters={"chaco": FakeAdapter()}, now_fn=clock)
    with pytest.raises(WrongDataMode):
        await demo.poll_now("chaco")


async def test_rate_limited_task_is_requeued(session_factory):
    clock = Clock()
    browser = FakeAdapter("wu", method="browser")
    collector = Collector(session_factory, make_settings(), adapters={"wu": browser}, now_fn=clock)
    await collector.collect(browser, force=True)  # the scheduler just ran this source
    queued = await collector.request_quote("wu", {"amount": "5000"})
    assert queued["status"] == "queued"
    assert await collector.process_tasks() == 0 and browser.calls == 1
    with session_factory() as s:
        task = s.get(Task, queued["job_id"])
        assert task.status == "queued" and task.started_at is None  # back in the queue, not "running since"
    clock.t = NOW + timedelta(seconds=61)
    assert await collector.process_tasks() == 1 and browser.calls == 2
    with session_factory() as s:
        assert s.get(Task, queued["job_id"]).status == "done"


@respx.mock
async def test_conditional_get_skips_parse_on_304_and_stores_validators(session_factory, tmp_path):
    """B8/B9: the collector GETs with the stored validators, keeps ETag/Last-Modified in watch_states,
    writes the raw payload under EVIDENCE_DIR and treats a 304 as "unchanged" without parsing."""
    settings = make_settings(evidence_dir=str(tmp_path))
    clock = Clock()
    adapter = ConditionalAdapter()
    collector = Collector(session_factory, settings, adapters={"chaco": adapter}, now_fn=clock)
    body = "<table>USD 7300 7350</table>"
    route = respx.get(adapter.info.url).mock(
        return_value=httpx.Response(200, text=body, headers={"ETag": '"v1"', "Last-Modified": LAST_MODIFIED})
    )

    out = (await collector.run_once())[0]
    assert adapter.calls == 0 and adapter.parsed == 1 and route.call_count == 1
    assert out.quotes_stored == 1 and out.health == "ok" and out.new_capture and not out.skipped
    sent = route.calls.last.request.headers
    assert "If-None-Match" not in sent and "If-Modified-Since" not in sent
    with session_factory() as s:
        ws = s.get(WatchState, "chaco")
        assert ws.etag == '"v1"' and ws.last_modified == LAST_MODIFIED
        ev = s.scalars(select(Evidence)).one()
        assert ev.raw_path is not None
        raw = Path(ev.raw_path)
        assert raw.is_relative_to(tmp_path) and raw.read_text() == body
        assert ev.sha256 == hashlib.sha256(body.encode()).hexdigest()

    clock.t = NOW + timedelta(seconds=301)
    route.mock(return_value=httpx.Response(304))
    out = (await collector.run_once())[0]
    sent = route.calls.last.request.headers
    assert sent["If-None-Match"] == '"v1"' and sent["If-Modified-Since"] == LAST_MODIFIED
    assert out.status == "not_modified" and out.new_capture is False and out.quotes_stored == 0
    assert not out.skipped and out.health == "ok"
    assert adapter.parsed == 1 and adapter.calls == 0
    with session_factory() as s:
        ws = s.get(WatchState, "chaco")
        assert ws.last_run_at == clock.t and ws.interval_s == 450  # unchanged => interval grows
        assert ws.etag == '"v1"' and ws.last_modified == LAST_MODIFIED
        assert s.scalar(select(func.count(Quote.id))) == 1
        assert s.scalar(select(func.count(Evidence.id))) == 1


@respx.mock
async def test_conditional_get_blocked_is_recorded_without_second_request(session_factory):
    adapter = ConditionalAdapter()
    collector = Collector(session_factory, make_settings(), adapters={"chaco": adapter}, now_fn=Clock())
    route = respx.get(adapter.info.url).mock(return_value=httpx.Response(403, text="Access denied"))
    out = (await collector.run_once())[0]
    assert out.health == "blocked" and "403" in (out.message or "")
    assert adapter.calls == 0 and adapter.parsed == 0 and route.call_count == 1
    with session_factory() as s:
        src = s.get(Source, "chaco")
        assert src.health == "blocked" and src.consecutive_failures == 1


async def test_on_demand_request_uses_adapter_fetch(session_factory):
    """Requests with parameters go through the adapter's own `fetch` (forms, amounts); no collector GET."""
    adapter = ConditionalAdapter()
    collector = Collector(session_factory, make_settings(), adapters={"chaco": adapter}, now_fn=Clock())
    done = await collector.request_quote("chaco", {"base": "USD", "quote": "PYG"})
    assert done["status"] == "done" and adapter.calls == 1 and adapter.parsed == 0
