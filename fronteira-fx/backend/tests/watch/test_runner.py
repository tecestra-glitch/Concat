from __future__ import annotations

import asyncio

from fronteira_fx.watch.runner import run_forever
from fronteira_fx.watch.scheduler import Scheduler, SchedulerConfig
from fronteira_fx.watch.service import WatchService
from tests.watch.conftest import FakeAdapter, info, quote, result


async def test_runner_polls_due_sources_and_stops_gracefully():
    adapters = {
        f"s{i}": FakeAdapter(info(f"s{i}", method="browser"), results=[result(quote(), source_id=f"s{i}")])
        for i in range(3)
    }
    svc = WatchService(adapters=adapters, scheduler=Scheduler(SchedulerConfig(min_interval_s=1, max_interval_s=2)))
    stop = asyncio.Event()
    outcomes = []
    task = asyncio.create_task(run_forever(svc, concurrency=2, stop=stop, tick_s=0.01, max_sleep_s=0.05,
                                           on_outcome=outcomes.append))
    for _ in range(200):
        await asyncio.sleep(0.01)
        if len(outcomes) >= 3:
            break
    stop.set()
    await asyncio.wait_for(task, timeout=2)
    assert {o.source_id for o in outcomes} >= {"s0", "s1", "s2"}
    assert all(a.fetch_calls >= 1 for a in adapters.values())
    assert all(not s.running for s in svc.scheduler.sources())


async def test_runner_waits_for_in_flight_poll_on_shutdown():
    started = asyncio.Event()
    release = asyncio.Event()

    class Slow(FakeAdapter):
        async def fetch(self, **params):
            started.set()
            await release.wait()
            return await super().fetch(**params)

    adapter = Slow(info("slow", method="browser"), results=[result(quote(), source_id="slow")])
    svc = WatchService(adapters={"slow": adapter})
    stop = asyncio.Event()
    task = asyncio.create_task(run_forever(svc, stop=stop, tick_s=0.01, max_sleep_s=0.05, shutdown_grace_s=1))
    await asyncio.wait_for(started.wait(), timeout=2)
    stop.set()
    await asyncio.sleep(0.05)
    assert not task.done()  # waiting for the in-flight poll
    release.set()
    await asyncio.wait_for(task, timeout=2)
    assert adapter.fetch_calls == 1 and svc.statuses()[0].status == "ok"


async def test_runner_survives_a_poll_that_raises(monkeypatch):
    adapter = FakeAdapter(info("x", method="browser"), results=[result(quote(), source_id="x")])
    svc = WatchService(adapters={"x": adapter}, scheduler=Scheduler(SchedulerConfig(min_interval_s=1, max_interval_s=1)))
    calls = 0
    real_poll = svc.poll

    async def flaky(source_id: str, **kw):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("unexpected")
        return await real_poll(source_id, **kw)

    monkeypatch.setattr(svc, "poll", flaky)
    stop = asyncio.Event()
    task = asyncio.create_task(run_forever(svc, stop=stop, tick_s=0.01, max_sleep_s=0.05))
    for _ in range(300):
        await asyncio.sleep(0.01)
        if calls >= 2:
            break
    stop.set()
    await asyncio.wait_for(task, timeout=2)
    assert calls >= 2 and svc.scheduler.get("x").errors_in_row == 0
