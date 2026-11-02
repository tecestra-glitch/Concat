from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from fronteira_fx.adapters.base import AdapterInfo, AdapterResult, AdapterStatus, EvidenceDraft, Fee, QuoteDraft
from fronteira_fx.models import Evidence, Opportunity, Quote, QuoteEvent, Source, Task
from fronteira_fx.services.collector import Collector, backoff_delay
from tests.conftest import NOW, make_settings

D = Decimal


class FakeAdapter:
    def __init__(
        self, source_id="chaco", *, status=AdapterStatus.OK, sha="abc", method="html", quotes=None, raise_exc=False
    ):
        self.info = AdapterInfo(
            id=source_id,
            name=source_id.title(),
            kind="exchange_house",
            method=method,
            url=f"https://{source_id}.example",
            capabilities=["buy_sell"],
            limitations=[],
            cities=["CDE"],
            currencies=["USD", "PYG"],
            poll_interval_s=300,
        )
        self.status = status
        self.sha = sha
        self.calls = 0
        self.raise_exc = raise_exc
        self.quotes = quotes

    def _quotes(self):
        if self.quotes is not None:
            return self.quotes
        return [
            QuoteDraft(
                source_id=self.info.id,
                base="USD",
                quote="PYG",
                buy=D("7300"),
                sell=D("7350"),
                unit_note="PYG por 1 USD",
                modality="cash",
                kind="indicative",
                channel="physical",
                city="CDE",
                branch_id=f"{self.info.id}-cde",
                fees=[Fee("tarifa", D("0"), "PYG")],
                declared_updated_at=datetime(2026, 11, 2, 11, 0, tzinfo=UTC),
            )
        ]

    async def fetch(self, **params):
        self.calls += 1
        if self.raise_exc:
            raise RuntimeError("boom")
        if self.status in (AdapterStatus.BLOCKED, AdapterStatus.ERROR):
            return AdapterResult(status=self.status, quotes=[], evidence=None, message="403 anti-bot")
        ev = EvidenceDraft(
            source_id=self.info.id,
            kind="html",
            url=self.info.url,
            captured_at=NOW,
            sha256=self.sha,
            excerpt="<table>...</table>",
            rules=["parser v1"],
        )
        return AdapterResult(status=self.status, quotes=self._quotes(), evidence=ev)

    def parse(self, raw, *, captured_at, url, **params):
        raise NotImplementedError


class Clock:
    def __init__(self, t=NOW):
        self.t = t

    def __call__(self):
        return self.t


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
