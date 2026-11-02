from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest

from fronteira_fx.adapters.base import AdapterStatus
from fronteira_fx.watch.fetcher import FetchOutcome
from fronteira_fx.watch.scheduler import Scheduler, SchedulerConfig
from fronteira_fx.watch.service import PollOutcome, UnknownSource, WatchService
from fronteira_fx.watch.store import InMemoryWatchStore
from tests.watch.conftest import FakeAdapter, FakeClock, info, quote, result


class FakeFetch:
    """Scripted conditional_get replacement: each call pops the next (status, body, etag)."""

    def __init__(self) -> None:
        self.script: list[FetchOutcome] = []
        self.calls: list[dict[str, Any]] = []

    def push(self, *, status_code: int = 200, body: str | None = "page", etag: str | None = None,
             not_modified: bool = False, error: str | None = None, blocked: bool = False) -> None:
        self.script.append(FetchOutcome(
            url="https://fake.example/cotizaciones", status_code=status_code, body=body, etag=etag,
            last_modified=None, not_modified=not_modified, elapsed_ms=12, error=error, blocked=blocked,
        ))

    async def __call__(self, url: str, *, etag: str | None = None, last_modified: str | None = None) -> FetchOutcome:
        self.calls.append({"url": url, "etag": etag, "last_modified": last_modified})
        out = self.script.pop(0)
        if out.not_modified and out.etag is None:
            out.etag = etag
        return out


def make_service(clock: FakeClock, adapters: dict, **kw) -> tuple[WatchService, list[tuple[str, dict]]]:
    events: list[tuple[str, dict]] = []
    scheduler = Scheduler(SchedulerConfig(jitter=0.0), clock=clock)
    svc = WatchService(
        store=InMemoryWatchStore(), scheduler=scheduler, adapters=adapters, clock=clock,
        emit=lambda t, p: events.append((t, p)), **kw,
    )
    return svc, events


async def test_browser_adapter_changes_are_emitted_exactly_once(clock):
    adapter = FakeAdapter(info("fake", method="browser"), results=[
        result(quote(buy="7290", sell="7350")),
        result(quote(buy="7290", sell="7350")),  # identical re-poll
        result(quote(buy="7290", sell="7360")),  # real change
        result(quote(buy="7290.00", sell="7360.0")),  # same numbers, different formatting
    ])
    svc, events = make_service(clock, {"fake": adapter})
    first = await svc.poll("fake")
    assert isinstance(first, PollOutcome) and first.changes == [] and first.change is None
    assert first.status.status == "ok" and first.status.content_hash and first.status.mode == "adapter_fetch"
    assert first.status.last_run_at == clock.now and first.status.next_run_at == clock.now + timedelta(seconds=300)
    clock.advance(300)
    second = await svc.poll("fake")
    assert second.changes == [] and events == []
    clock.advance(300)
    third = await svc.poll("fake")
    assert [c.summary for c in third.changes] == ["USD/PYG CDE venda 7350 → 7360"]
    assert third.change is not None and third.change.kind == "quote_change"
    assert third.status.last_change_at == clock.now and third.status.changes_24h == 1
    assert third.status.interval_s == 150  # shortened after a real change
    clock.advance(150)
    fourth = await svc.poll("fake")
    assert fourth.changes == []
    assert len(events) == 1
    type_, payload = events[0]
    assert type_ == "source.change" and payload["summary"] == "USD/PYG CDE venda 7350 → 7360"
    assert payload["source_id"] == "fake" and payload["kind"] == "quote_change" and isinstance(payload["ts"], str)
    assert [c.summary for c in svc.list_changes()] == ["USD/PYG CDE venda 7350 → 7360"]
    assert adapter.fetch_calls == 4 and adapter.parse_calls == 0


async def test_conditional_get_path_uses_validators_and_skips_parse_on_304(clock):
    adapter = FakeAdapter(info("fake", method="html"), results=[
        result(quote(buy="7290", sell="7350")),
        result(quote(buy="7300", sell="7350")),
    ])
    fetch = FakeFetch()
    fetch.push(body="v1", etag='"e1"')
    fetch.push(status_code=304, body=None, not_modified=True)
    fetch.push(body="v2", etag='"e2"')
    svc, events = make_service(clock, {"fake": adapter}, fetch=fetch)

    o1 = await svc.poll("fake")
    assert fetch.calls[0] == {"url": "https://fake.example/cotizaciones", "etag": None, "last_modified": None}
    assert o1.status.etag == '"e1"' and o1.status.mode == "conditional_get" and adapter.parse_calls == 1
    assert adapter.parsed_bodies == ["v1"] and o1.elapsed_ms == 12

    o2 = await svc.poll("fake")
    assert fetch.calls[1]["etag"] == '"e1"'
    assert o2.not_modified is True and o2.result is None and o2.changes == [] and adapter.parse_calls == 1
    assert o2.status.status == "ok" and o2.status.content_hash == o1.status.content_hash
    assert o2.status.etag == '"e1"'

    o3 = await svc.poll("fake")
    assert fetch.calls[2]["etag"] == '"e1"'
    assert [c.summary for c in o3.changes] == ["USD/PYG CDE compra 7290 → 7300"]
    assert o3.status.etag == '"e2"' and len(events) == 1
    assert adapter.fetch_calls == 0

    # force=True drops the validators
    fetch.push(body="v3", etag='"e3"')
    await svc.poll("fake", force=True)
    assert fetch.calls[3]["etag"] is None and fetch.calls[3]["last_modified"] is None


async def test_blocked_fetch_backs_off_and_recovery_is_a_status_change(clock):
    adapter = FakeAdapter(info("fake", method="html"), results=[result(quote())])
    fetch = FakeFetch()
    fetch.push(body="v1", etag='"e1"')
    fetch.push(status_code=403, body=None, error="HTTP 403: blocked by anti-bot/WAF", blocked=True)
    fetch.push(body=None, status_code=None, error="timeout after 20s")
    fetch.push(body="v1", etag='"e1"')
    svc, events = make_service(clock, {"fake": adapter}, fetch=fetch)
    await svc.poll("fake")
    blocked = await svc.poll("fake")
    assert blocked.status.status == "blocked" and blocked.status.errors_in_row == 1
    assert blocked.status.last_error == "HTTP 403: blocked by anti-bot/WAF"
    assert blocked.status.etag == '"e1"'  # validators survive a block
    assert (blocked.status.next_run_at - clock.now).total_seconds() == 1200  # 300 * 2**2, no jitter
    assert [c.kind for c in blocked.changes] == ["status_change"]
    errored = await svc.poll("fake")
    assert errored.status.status == "error" and errored.status.errors_in_row == 2
    assert errored.status.last_error == "timeout after 20s"
    assert [c.kind for c in errored.changes] == ["status_change"]  # blocked -> error
    back = await svc.poll("fake")
    assert back.status.status == "ok" and back.status.errors_in_row == 0 and back.status.last_error is None
    assert [c.summary for c in back.changes] == ["status error → ok"]
    assert [e[1]["kind"] for e in events] == ["status_change", "status_change", "status_change"]
    kinds = {c.kind for c in svc.list_changes(kind="status_change")}
    assert kinds == {"status_change"} and svc.list_changes(kind="quote_change") == []


async def test_layout_change_when_parser_breaks(clock):
    adapter = FakeAdapter(info("fake", method="browser"), results=[
        result(quote(), quote("BRL", "PYG", "1360", "1384")),
        result(status=AdapterStatus.ERROR, message="no quotes parsed (layout changed?)"),
    ])
    svc, events = make_service(clock, {"fake": adapter})
    await svc.poll("fake")
    out = await svc.poll("fake")
    assert out.change is not None and out.change.kind == "layout_change"
    assert out.status.status == "error" and out.status.errors_in_row == 1
    assert out.status.interval_s == 300  # a layout change is not a "real change": no shortening


async def test_adapter_exceptions_and_timeouts_become_error_status(clock):
    adapter = FakeAdapter(info("fake", method="browser"), results=[result(quote())], raise_on_fetch=RuntimeError("boom"))
    svc, _ = make_service(clock, {"fake": adapter})
    out = await svc.poll("fake")
    assert out.status.status == "error" and out.status.last_error == "RuntimeError: boom"

    class Slow:
        info = info("slow", method="browser")

        async def fetch(self, **params):
            import asyncio

            await asyncio.sleep(1)
            return result(quote())

        def parse(self, raw, *, captured_at, url, **params):
            return result(quote())

    svc2, _ = make_service(clock, {"slow": Slow()}, adapter_timeout_s=0.01)
    out = await svc2.poll("slow")
    assert out.status.status == "error" and "timeout" in out.status.last_error


async def test_parse_exception_is_contained(clock):
    class Broken(FakeAdapter):
        def parse(self, raw, *, captured_at, url, **params):
            raise ValueError("bad html")

    fetch = FakeFetch()
    fetch.push(body="x")
    svc, _ = make_service(clock, {"fake": Broken(info("fake"))}, fetch=fetch)
    out = await svc.poll("fake")
    assert out.status.status == "error" and out.status.last_error == "parse failed: ValueError: bad html"


async def test_manual_sources_are_disabled_and_unknown_sources_raise(clock):
    svc, _ = make_service(clock, {"manual": FakeAdapter(info("manual", method="manual"))})
    statuses = svc.statuses()
    assert len(statuses) == 1 and statuses[0].enabled is False and statuses[0].mode == "disabled"
    assert statuses[0].status == "stale" and statuses[0].next_run_at is None
    with pytest.raises(UnknownSource):
        await svc.poll("nope")
    with pytest.raises(UnknownSource):
        svc.update_source("nope", enabled=True)


async def test_update_source_override_and_persistence(clock):
    adapter = FakeAdapter(info("fake", method="browser"), results=[result(quote())])
    svc, _ = make_service(clock, {"fake": adapter})
    st = svc.update_source("fake", interval_s=30)
    assert st.interval_s == 60 and st.interval_override_s == 60  # clamped to the floor
    st = svc.update_source("fake", enabled=False)
    assert st.enabled is False and st.next_run_at is None
    assert svc.store.load_status("fake").enabled is False
    # a manual poll still works while disabled
    out = await svc.poll("fake")
    assert out.status.status == "ok" and out.status.enabled is False and out.status.next_run_at is None
    st = svc.update_source("fake", enabled=True)
    assert st.enabled is True and st.next_run_at == clock.now
    assert svc.statuses()[0].interval_override_s == 60
    st = svc.request_run("fake")
    assert svc.scheduler.due() == ["fake"]


async def test_state_survives_a_restart_through_the_store(clock):
    store = InMemoryWatchStore()
    adapter = FakeAdapter(info("fake", method="html"), results=[result(quote(buy="7290", sell="7350"))])
    fetch = FakeFetch()
    fetch.push(body="v1", etag='"e1"')
    svc = WatchService(store=store, scheduler=Scheduler(clock=clock), adapters={"fake": adapter}, fetch=fetch, clock=clock)
    svc.update_source("fake", interval_s=120)
    await svc.poll("fake")
    clock.advance(60)
    # new process: same store, new service, new adapter instance with a moved price
    adapter2 = FakeAdapter(info("fake", method="html"), results=[result(quote(buy="7290", sell="7361"))])
    fetch2 = FakeFetch()
    fetch2.push(body="v2", etag='"e2"')
    events: list = []
    svc2 = WatchService(store=store, scheduler=Scheduler(clock=clock), adapters={"fake": adapter2}, fetch=fetch2,
                        clock=clock, emit=lambda t, p: events.append(p))
    restored = svc2.statuses()[0]
    assert restored.etag == '"e1"' and restored.interval_override_s == 120 and restored.status == "ok"
    assert restored.content_hash and restored.last_run_at == clock.now - timedelta(seconds=60)
    assert svc2.scheduler.due() == []  # next_run_at restored (60 s left)
    out = await svc2.poll("fake")
    assert fetch2.calls[0]["etag"] == '"e1"'
    assert [c.summary for c in out.changes] == ["USD/PYG CDE venda 7350 → 7361"]
    assert len(events) == 1


async def test_on_result_hook_and_async_emit(clock):
    seen: list[str] = []
    emitted: list[str] = []

    async def on_result(source_id: str, res) -> None:
        seen.append(f"{source_id}:{res.status}:{len(res.quotes)}")

    async def emit(type_: str, payload: dict) -> None:
        emitted.append(type_)

    adapter = FakeAdapter(info("fake", method="browser"), results=[result(quote()), result(quote(sell="7400"))])
    svc = WatchService(adapters={"fake": adapter}, clock=clock, emit=emit, on_result=on_result)
    await svc.poll("fake")
    await svc.poll("fake")
    assert seen == ["fake:ok:1", "fake:ok:1"] and emitted == ["source.change"]


async def test_hook_failures_do_not_break_polling(clock):
    def bad_emit(type_, payload):
        raise RuntimeError("bridge down")

    def bad_hook(source_id, res):
        raise RuntimeError("db down")

    adapter = FakeAdapter(info("fake", method="browser"), results=[result(quote()), result(quote(sell="7400"))])
    svc = WatchService(adapters={"fake": adapter}, clock=clock, emit=bad_emit, on_result=bad_hook)
    await svc.poll("fake")
    out = await svc.poll("fake")
    assert len(out.changes) == 1 and out.status.status == "ok"
    assert len(svc.list_changes()) == 1  # still persisted


def test_registry_is_loaded_lazily_and_tolerates_absence(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.endswith("adapters.registry"):
            raise ImportError("not yet")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    svc = WatchService()
    assert svc.adapters() == {} and svc.statuses() == []
