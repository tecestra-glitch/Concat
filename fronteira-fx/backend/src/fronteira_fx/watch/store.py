"""Persistence boundary of the watch module.

`WatchStore` is a small Protocol so the service can be tested with `InMemoryWatchStore` and run in
production with `store_sql.SqlWatchStore`. All methods are synchronous and cheap (local DB rows).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from .schemas import Change, WatchStatus


class WatchStore(Protocol):
    def save_status(self, status: WatchStatus) -> None: ...

    def load_status(self, source_id: str) -> WatchStatus | None: ...

    def list_status(self) -> list[WatchStatus]: ...

    def save_snapshot(self, source_id: str, snapshot: dict[str, Any]) -> None:
        """Canonical quotes of the last poll (see `diff.Snapshot.to_json`), so diffs survive restarts."""
        ...

    def load_snapshot(self, source_id: str) -> dict[str, Any] | None: ...

    def save_change(self, change: Change) -> None: ...

    def list_changes(
        self,
        *,
        source_id: str | None = None,
        since: datetime | None = None,
        kind: str | None = None,
        limit: int = 200,
    ) -> list[Change]:
        """Newest first."""
        ...

    def count_changes(self, source_id: str, *, since: datetime) -> int: ...


class InMemoryWatchStore:
    """Dict-backed store for tests and for `python -m fronteira_fx.watch` without a database."""

    def __init__(self) -> None:
        self._status: dict[str, WatchStatus] = {}
        self._snapshots: dict[str, dict[str, Any]] = {}
        self._changes: list[Change] = []

    def save_status(self, status: WatchStatus) -> None:
        self._status[status.source_id] = status.model_copy(deep=True)

    def load_status(self, source_id: str) -> WatchStatus | None:
        st = self._status.get(source_id)
        return st.model_copy(deep=True) if st else None

    def list_status(self) -> list[WatchStatus]:
        return [self._status[k].model_copy(deep=True) for k in sorted(self._status)]

    def save_snapshot(self, source_id: str, snapshot: dict[str, Any]) -> None:
        self._snapshots[source_id] = snapshot

    def load_snapshot(self, source_id: str) -> dict[str, Any] | None:
        return self._snapshots.get(source_id)

    def save_change(self, change: Change) -> None:
        self._changes.append(change.model_copy(deep=True))

    def list_changes(
        self,
        *,
        source_id: str | None = None,
        since: datetime | None = None,
        kind: str | None = None,
        limit: int = 200,
    ) -> list[Change]:
        rows = [
            c
            for c in self._changes
            if (source_id is None or c.source_id == source_id)
            and (kind is None or c.kind == kind)
            and (since is None or c.ts >= since)
        ]
        rows.sort(key=lambda c: c.ts, reverse=True)
        return [c.model_copy(deep=True) for c in rows[:limit]]

    def count_changes(self, source_id: str, *, since: datetime) -> int:
        return sum(1 for c in self._changes if c.source_id == source_id and c.ts >= since)
