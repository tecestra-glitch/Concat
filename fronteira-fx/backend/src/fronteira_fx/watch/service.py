"""`WatchService`: fetch -> adapter.parse/fetch -> diff -> store + events, for every adapter.

Fetch modes (by `AdapterInfo.method`, overridable):

* ``html``                       -> conditional GET of `info.url` + `adapter.parse()`;
* ``official_api`` / ``browser`` -> `adapter.fetch()` (the adapter knows its endpoints / needs a browser);
* ``manual``                     -> disabled (nothing to poll).

Events go through `emit(type, payload)`; the only type emitted here is ``source.change`` with a
`Change` payload (JSON-ready). The core bridges it to its own event stream. Fresh `AdapterResult`s
are offered to `on_result(source_id, result)` so the core can store quotes/evidence.
"""
from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from ..adapters.base import Adapter, AdapterInfo, AdapterResult, AdapterStatus
from .diff import Snapshot, diff_snapshots
from .fetcher import FetchOutcome, conditional_get
from .scheduler import Clock, Scheduler, SourceSchedule, utcnow
from .schemas import Change, FetchMode, WatchStatus
from .store import InMemoryWatchStore, WatchStore

log = logging.getLogger("fronteira_fx.watch")

EmitFn = Callable[[str, dict[str, Any]], Awaitable[None] | None]
ResultHook = Callable[[str, AdapterResult], Awaitable[None] | None]
FetchFn = Callable[..., Awaitable[FetchOutcome]]

DEFAULT_MODES: dict[str, FetchMode] = {
    "html": "conditional_get",
    "official_api": "adapter_fetch",
    "browser": "adapter_fetch",
    "manual": "disabled",
}
_FAILURES = {AdapterStatus.ERROR, AdapterStatus.BLOCKED, AdapterStatus.NEEDS_SESSION}
_BLOCKED = {AdapterStatus.BLOCKED, AdapterStatus.NEEDS_SESSION}


class UnknownSource(KeyError):
    pass


def load_registry() -> dict[str, Adapter]:
    """Lazy, tolerant import of the adapter registry (owned by another module)."""
    try:
        from ..adapters.registry import ADAPTERS  # type: ignore[import-not-found]
    except Exception as exc:  # registry missing or broken: watch nothing instead of crashing
        log.warning("adapter registry unavailable: %s", exc)
        return {}
    return dict(ADAPTERS)


@dataclass(slots=True)
class PollOutcome:
    source_id: str
    status: WatchStatus
    changes: list[Change] = field(default_factory=list)
    result: AdapterResult | None = None  # None when the page was not modified (304)
    not_modified: bool = False
    elapsed_ms: int = 0

    @property
    def change(self) -> Change | None:
        """Most significant change of this poll (layout > status > quotes), or None."""
        return self.changes[0] if self.changes else None


@dataclass(slots=True)
class _Last:
    status: str = "stale"
    error: str | None = None
    content_hash: str | None = None
    etag: str | None = None
    last_modified: str | None = None


class WatchService:
    def __init__(
        self,
        *,
        store: WatchStore | None = None,
        scheduler: Scheduler | None = None,
        adapters: Mapping[str, Adapter] | None = None,
        emit: EmitFn | None = None,
        on_result: ResultHook | None = None,
        fetch: FetchFn = conditional_get,
        clock: Clock = utcnow,
        modes: Mapping[str, FetchMode] | None = None,
        adapter_timeout_s: float = 120.0,
    ) -> None:
        self.clock = clock
        self.store: WatchStore = store if store is not None else InMemoryWatchStore()
        self.scheduler = scheduler if scheduler is not None else Scheduler(clock=clock)
        self._adapters: dict[str, Adapter] | None = dict(adapters) if adapters is not None else None
        self.emit = emit
        self.on_result = on_result
        self.fetch = fetch
        self.modes = dict(DEFAULT_MODES, **(modes or {}))
        self.adapter_timeout_s = adapter_timeout_s
        self._snapshots: dict[str, Snapshot] = {}
        self._last: dict[str, _Last] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._registered = False

    # ------------------------------------------------------------------ registry
    def adapters(self) -> dict[str, Adapter]:
        if self._adapters is None:
            self._adapters = load_registry()
        return self._adapters

    def mode_for(self, info: AdapterInfo) -> FetchMode:
        return self.modes.get(info.method, "adapter_fetch")

    def register_sources(self) -> None:
        """Teach the scheduler every adapter, restoring persisted state. Idempotent."""
        for source_id, adapter in sorted(self.adapters().items()):
            if source_id not in self.scheduler:
                self._register(source_id, adapter)
        self._registered = True

    def _register(self, source_id: str, adapter: Adapter) -> SourceSchedule:
        info = adapter.info
        saved = self.store.load_status(source_id)
        mode = self.mode_for(info)
        enabled = (saved.enabled if saved is not None else True) and mode != "disabled"
        sched = self.scheduler.add_source(
            source_id,
            info.poll_interval_s,
            enabled=enabled,
            interval_s=saved.interval_s if saved is not None else None,
            manual_interval_s=saved.interval_override_s if saved is not None else None,
            first_run_at=saved.next_run_at if saved is not None and saved.next_run_at else None,
        )
        last = _Last()
        if saved is not None:
            sched.errors_in_row = saved.errors_in_row
            sched.last_run_at = saved.last_run_at
            sched.last_change_at = saved.last_change_at
            last = _Last(saved.status, saved.last_error, saved.content_hash, saved.etag, saved.last_modified)
            snap = Snapshot.from_json(self.store.load_snapshot(source_id))
            if snap is not None:
                self._snapshots[source_id] = snap
        self._last[source_id] = last
        return sched

    def _adapter(self, source_id: str) -> Adapter:
        try:
            adapter = self.adapters()[source_id]
        except KeyError:
            raise UnknownSource(source_id) from None
        if source_id not in self.scheduler:
            self._register(source_id, adapter)
        return adapter

    def _lock(self, source_id: str) -> asyncio.Lock:
        lock = self._locks.get(source_id)
        if lock is None:
            lock = self._locks[source_id] = asyncio.Lock()
        return lock

    # ------------------------------------------------------------------ polling
    async def poll(self, source_id: str, *, force: bool = False) -> PollOutcome:
        """Poll one source now (regardless of schedule). `force` skips the HTTP validators (no 304)."""
        adapter = self._adapter(source_id)
        async with self._lock(source_id):
            now = self.clock()
            self.scheduler.mark_started(source_id, now)
            mode = self.mode_for(adapter.info)
            last = self._last.setdefault(source_id, _Last())
            fetched: FetchOutcome | None = None
            result: AdapterResult | None
            if mode == "disabled":
                result = _failure(AdapterStatus.ERROR, "fonte manual: sem sondagem automática")
            elif mode == "conditional_get":
                fetched = await self.fetch(
                    adapter.info.url,
                    etag=None if force else last.etag,
                    last_modified=None if force else last.last_modified,
                )
                if fetched.error is not None:
                    status = AdapterStatus.BLOCKED if fetched.blocked else AdapterStatus.ERROR
                    result = _failure(status, fetched.error)
                elif fetched.not_modified:
                    result = None
                else:
                    result = self._parse(adapter, fetched, now)
                if fetched.error is None:
                    last.etag, last.last_modified = fetched.etag, fetched.last_modified
            else:
                result = await self._adapter_fetch(adapter)
            return await self._finish(source_id, adapter, result, now, elapsed_ms=fetched.elapsed_ms if fetched else 0)

    def _parse(self, adapter: Adapter, fetched: FetchOutcome, now: datetime) -> AdapterResult:
        try:
            return adapter.parse(fetched.body or "", captured_at=now, url=fetched.url)
        except Exception as exc:  # a parser bug must not kill the loop
            log.exception("adapter %s parse raised", adapter.info.id)
            return _failure(AdapterStatus.ERROR, f"parse failed: {type(exc).__name__}: {exc}")

    async def _adapter_fetch(self, adapter: Adapter) -> AdapterResult:
        try:
            return await asyncio.wait_for(adapter.fetch(), timeout=self.adapter_timeout_s)
        except TimeoutError:
            return _failure(AdapterStatus.ERROR, f"adapter timeout after {self.adapter_timeout_s:g}s")
        except Exception as exc:
            log.exception("adapter %s fetch raised", adapter.info.id)
            return _failure(AdapterStatus.ERROR, f"{type(exc).__name__}: {exc}")

    async def _finish(
        self, source_id: str, adapter: Adapter, result: AdapterResult | None, now: datetime, *, elapsed_ms: int
    ) -> PollOutcome:
        last = self._last[source_id]
        previous = self._snapshots.get(source_id)
        changes: list[Change] = []
        if result is not None:
            snapshot = Snapshot.from_result(result)
            changes = diff_snapshots(previous, snapshot, source_id=source_id, ts=now)
            self._snapshots[source_id] = snapshot
            self.store.save_snapshot(source_id, snapshot.to_json())
            last.status = str(result.status)
            last.error = result.message if result.status != AdapterStatus.OK else None
            last.content_hash = snapshot.hash
            is_error = result.status in _FAILURES
            blocked = result.status in _BLOCKED
        else:
            is_error = blocked = False
        changed = any(c.kind == "quote_change" for c in changes)
        sched = self.scheduler.record_result(
            source_id, changed=changed, error=is_error and not blocked, blocked=blocked, now=now
        )
        for change in changes:
            self.store.save_change(change)
            await self._emit("source.change", change.model_dump(mode="json"))
        if result is not None and self.on_result is not None:
            try:
                await _maybe_await(self.on_result(source_id, result))
            except Exception:
                log.exception("on_result hook failed for %s", source_id)
        status = self._status_for(source_id, adapter.info, sched, now)
        self.store.save_status(status)
        return PollOutcome(
            source_id=source_id, status=status, changes=changes, result=result, not_modified=result is None,
            elapsed_ms=elapsed_ms,
        )

    async def _emit(self, type_: str, payload: dict[str, Any]) -> None:
        if self.emit is None:
            return
        try:
            await _maybe_await(self.emit(type_, payload))
        except Exception:
            log.exception("emit(%s) failed", type_)

    # ------------------------------------------------------------------ status / control
    def _status_for(self, source_id: str, info: AdapterInfo, sched: SourceSchedule, now: datetime) -> WatchStatus:
        last = self._last.setdefault(source_id, _Last())
        return WatchStatus(
            source_id=source_id,
            enabled=sched.enabled,
            interval_s=sched.interval_s,
            min_interval_s=sched.min_interval_s,
            max_interval_s=sched.max_interval_s,
            next_run_at=sched.next_run_at,
            last_run_at=sched.last_run_at,
            last_change_at=sched.last_change_at,
            changes_24h=self.store.count_changes(source_id, since=now - timedelta(hours=24)),
            errors_in_row=sched.errors_in_row,
            etag=last.etag,
            last_modified=last.last_modified,
            content_hash=last.content_hash,
            status=last.status,  # type: ignore[arg-type]
            last_error=last.error,
            interval_override_s=sched.manual_interval_s,
            mode=self.mode_for(info),
        )

    def status(self, source_id: str) -> WatchStatus:
        adapter = self._adapter(source_id)
        return self._status_for(source_id, adapter.info, self.scheduler.get(source_id), self.clock())

    def statuses(self) -> list[WatchStatus]:
        if not self._registered:
            self.register_sources()
        now = self.clock()
        return [
            self._status_for(sid, self.adapters()[sid].info, self.scheduler.get(sid), now)
            for sid in sorted(self.adapters())
        ]

    def update_source(
        self, source_id: str, *, interval_s: int | None = None, enabled: bool | None = None
    ) -> WatchStatus:
        adapter = self._adapter(source_id)
        now = self.clock()
        sched = self.scheduler.override(source_id, interval_s=interval_s, enabled=enabled, now=now)
        status = self._status_for(source_id, adapter.info, sched, now)
        self.store.save_status(status)
        return status

    def request_run(self, source_id: str) -> WatchStatus:
        """Ask the runner to poll ASAP (the route `trigger_poll` polls inline instead; see `poll`)."""
        adapter = self._adapter(source_id)
        sched = self.scheduler.run_now(source_id, self.clock())
        return self._status_for(source_id, adapter.info, sched, self.clock())

    def list_changes(
        self,
        *,
        source_id: str | None = None,
        since: datetime | None = None,
        kind: str | None = None,
        limit: int = 200,
    ) -> list[Change]:
        return self.store.list_changes(source_id=source_id, since=since, kind=kind, limit=limit)


def _failure(status: AdapterStatus, message: str) -> AdapterResult:
    return AdapterResult(status=status, quotes=[], evidence=None, message=message)


async def _maybe_await(value: Any) -> None:
    if inspect.isawaitable(value):
        await value
