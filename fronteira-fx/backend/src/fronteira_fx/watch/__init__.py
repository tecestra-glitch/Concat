"""Live monitoring of provider sites without an API: conditional fetch, content hashing, adaptive polling.

See docs/watch.md. Public surface:

* `WatchService` / `PollOutcome`      — orchestration (fetch -> parse -> diff -> store -> emit)
* `Scheduler` / `SchedulerConfig`     — adaptive per-source schedule (pure logic)
* `WatchStore`, `InMemoryWatchStore`  — persistence boundary (+ `store_sql.SqlWatchStore`)
* `router`, `get_service`, `set_service` — FastAPI router `/v1/watch`
* `run_forever`                       — polling loop
"""
from __future__ import annotations

from .diff import Snapshot, content_hash, diff_quotes, diff_results, diff_snapshots
from .fetcher import FetchOutcome, conditional_get
from .router import get_service, router, set_service
from .runner import run_forever
from .scheduler import Scheduler, SchedulerConfig, SourceSchedule
from .schemas import Change, WatchStatus, WatchUpdate
from .service import PollOutcome, UnknownSource, WatchService
from .store import InMemoryWatchStore, WatchStore

__all__ = [
    "Change",
    "FetchOutcome",
    "InMemoryWatchStore",
    "PollOutcome",
    "Scheduler",
    "SchedulerConfig",
    "Snapshot",
    "SourceSchedule",
    "UnknownSource",
    "WatchService",
    "WatchStatus",
    "WatchStore",
    "WatchUpdate",
    "conditional_get",
    "content_hash",
    "diff_quotes",
    "diff_results",
    "diff_snapshots",
    "get_service",
    "router",
    "run_forever",
    "set_service",
]
