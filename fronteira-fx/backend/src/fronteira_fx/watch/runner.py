"""Polling loop: dispatch due sources with bounded concurrency until asked to stop."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from .scheduler import Scheduler
from .service import PollOutcome, WatchService

log = logging.getLogger("fronteira_fx.watch.runner")


async def run_forever(
    service: WatchService,
    scheduler: Scheduler | None = None,
    *,
    concurrency: int = 4,
    stop: asyncio.Event | None = None,
    tick_s: float = 1.0,
    max_sleep_s: float = 30.0,
    shutdown_grace_s: float = 30.0,
    on_outcome: Callable[[PollOutcome], None] | None = None,
) -> None:
    """Run until `stop` is set. In-flight polls get `shutdown_grace_s` to finish, then are cancelled."""
    scheduler = scheduler or service.scheduler
    stop = stop or asyncio.Event()
    semaphore = asyncio.Semaphore(max(1, concurrency))
    tasks: set[asyncio.Task[None]] = set()
    service.register_sources()
    log.info("watch runner: %d source(s), concurrency %d", len(scheduler.sources()), concurrency)

    async def one(source_id: str) -> None:
        async with semaphore:
            try:
                outcome = await service.poll(source_id)
            except Exception:
                log.exception("poll %s failed", source_id)
                # make sure the source is not stuck in `running`
                try:
                    scheduler.record_result(source_id, changed=False, error=True)
                except KeyError:
                    pass
                return
            if outcome.changes:
                for change in outcome.changes:
                    log.info("%s: %s", source_id, change.summary)
            else:
                log.debug("%s: %s%s", source_id, outcome.status.status, " (304)" if outcome.not_modified else "")
            if on_outcome is not None:
                on_outcome(outcome)

    try:
        while not stop.is_set():
            now = service.clock()
            for source_id in scheduler.due(now):
                if len(tasks) >= concurrency:
                    break
                scheduler.mark_started(source_id, now)
                task = asyncio.create_task(one(source_id), name=f"watch:{source_id}")
                tasks.add(task)
                task.add_done_callback(tasks.discard)
            wake = scheduler.next_wakeup(now)
            delay = max_sleep_s if wake is None else min(max_sleep_s, max(tick_s, (wake - now).total_seconds()))
            if len(tasks) >= concurrency or (scheduler.due(now) and len(tasks) < concurrency):
                delay = tick_s
            try:
                await asyncio.wait_for(stop.wait(), timeout=delay)
            except TimeoutError:
                pass
    finally:
        if tasks:
            log.info("watch runner: waiting for %d in-flight poll(s)", len(tasks))
            _, pending = await asyncio.wait(tasks, timeout=shutdown_grace_s)
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
        log.info("watch runner stopped")
