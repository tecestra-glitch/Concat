"""SQLAlchemy implementation of `WatchStore` with its OWN tables (`watch_status`, `watch_changes`).

The tables live on a separate `DeclarativeBase` (`WatchBase`) so this module does not import the
core's `models.py`. Consequence for the core: Alembic must include `WatchBase.metadata` in its
`target_metadata` (or call `create_all(engine)` at start-up) for the tables to exist.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Engine, Integer, String, Text, create_engine, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool

from .schemas import Change, WatchStatus


class WatchBase(DeclarativeBase):
    pass


def _aware(dt: datetime | None) -> datetime | None:
    """SQLite drops tzinfo: everything we store is UTC, so put it back."""
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


class WatchStatusRow(WatchBase):
    __tablename__ = "watch_status"

    source_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    interval_s: Mapped[int] = mapped_column(Integer)
    min_interval_s: Mapped[int] = mapped_column(Integer)
    max_interval_s: Mapped[int] = mapped_column(Integer)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_change_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    errors_in_row: Mapped[int] = mapped_column(Integer, default=0)
    etag: Mapped[str | None] = mapped_column(String(512), nullable=True)
    last_modified: Mapped[str | None] = mapped_column(String(128), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="stale")
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    interval_override_s: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mode: Mapped[str] = mapped_column(String(32), default="adapter_fetch")
    snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(tz=UTC))

    def to_schema(self) -> WatchStatus:
        return WatchStatus(
            source_id=self.source_id,
            enabled=self.enabled,
            interval_s=self.interval_s,
            min_interval_s=self.min_interval_s,
            max_interval_s=self.max_interval_s,
            next_run_at=_aware(self.next_run_at),
            last_run_at=_aware(self.last_run_at),
            last_change_at=_aware(self.last_change_at),
            errors_in_row=self.errors_in_row,
            etag=self.etag,
            last_modified=self.last_modified,
            content_hash=self.content_hash,
            status=self.status,  # type: ignore[arg-type]
            last_error=self.last_error,
            interval_override_s=self.interval_override_s,
            mode=self.mode,  # type: ignore[arg-type]
        )


class WatchChangeRow(WatchBase):
    __tablename__ = "watch_changes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_id: Mapped[str] = mapped_column(String(64), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    summary: Mapped[str] = mapped_column(Text)
    before: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    after: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    evidence_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    def to_schema(self) -> Change:
        return Change(
            id=self.id,
            source_id=self.source_id,
            ts=_aware(self.ts) or datetime.now(tz=UTC),
            kind=self.kind,
            summary=self.summary,
            before=self.before or {},
            after=self.after or {},  # type: ignore[arg-type]
            evidence_id=self.evidence_id,
        )


def create_all(engine: Engine) -> None:
    WatchBase.metadata.create_all(engine)


class SqlWatchStore:
    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self.session_factory = session_factory

    @classmethod
    def from_url(cls, url: str, *, create: bool = True) -> SqlWatchStore:
        kwargs: dict[str, Any] = {"future": True}
        if url.startswith("sqlite") and (url == "sqlite://" or ":memory:" in url):
            kwargs.update(poolclass=StaticPool, connect_args={"check_same_thread": False})
        engine = create_engine(url, **kwargs)
        if create:
            create_all(engine)
        return cls(sessionmaker(engine, expire_on_commit=False))

    # ------------------------------------------------------------------ status
    def save_status(self, status: WatchStatus) -> None:
        with self.session_factory() as session, session.begin():
            row = session.get(WatchStatusRow, status.source_id)
            if row is None:
                row = WatchStatusRow(source_id=status.source_id)
                session.add(row)
            for name in (
                "enabled",
                "interval_s",
                "min_interval_s",
                "max_interval_s",
                "next_run_at",
                "last_run_at",
                "last_change_at",
                "errors_in_row",
                "etag",
                "last_modified",
                "content_hash",
                "status",
                "last_error",
                "interval_override_s",
                "mode",
            ):
                setattr(row, name, getattr(status, name))
            row.updated_at = datetime.now(tz=UTC)

    def load_status(self, source_id: str) -> WatchStatus | None:
        with self.session_factory() as session:
            row = session.get(WatchStatusRow, source_id)
            return row.to_schema() if row else None

    def list_status(self) -> list[WatchStatus]:
        with self.session_factory() as session:
            rows = session.scalars(select(WatchStatusRow).order_by(WatchStatusRow.source_id))
            return [r.to_schema() for r in rows]

    # ------------------------------------------------------------------ snapshots
    def save_snapshot(self, source_id: str, snapshot: dict[str, Any]) -> None:
        with self.session_factory() as session, session.begin():
            row = session.get(WatchStatusRow, source_id)
            if row is None:
                row = WatchStatusRow(source_id=source_id, interval_s=0, min_interval_s=0, max_interval_s=0)
                session.add(row)
            row.snapshot = snapshot

    def load_snapshot(self, source_id: str) -> dict[str, Any] | None:
        with self.session_factory() as session:
            row = session.get(WatchStatusRow, source_id)
            return row.snapshot if row else None

    # ------------------------------------------------------------------ changes
    def save_change(self, change: Change) -> None:
        with self.session_factory() as session, session.begin():
            session.merge(
                WatchChangeRow(
                    id=change.id,
                    source_id=change.source_id,
                    ts=change.ts,
                    kind=change.kind,
                    summary=change.summary,
                    before=change.before,
                    after=change.after,
                    evidence_id=change.evidence_id,
                )
            )

    def list_changes(
        self,
        *,
        source_id: str | None = None,
        since: datetime | None = None,
        kind: str | None = None,
        limit: int = 200,
    ) -> list[Change]:
        stmt = select(WatchChangeRow)
        if source_id is not None:
            stmt = stmt.where(WatchChangeRow.source_id == source_id)
        if kind is not None:
            stmt = stmt.where(WatchChangeRow.kind == kind)
        if since is not None:
            stmt = stmt.where(WatchChangeRow.ts >= since)
        stmt = stmt.order_by(WatchChangeRow.ts.desc(), WatchChangeRow.id.desc()).limit(limit)
        with self.session_factory() as session:
            return [r.to_schema() for r in session.scalars(stmt)]

    def count_changes(self, source_id: str, *, since: datetime) -> int:
        stmt = select(func.count(WatchChangeRow.id)).where(
            WatchChangeRow.source_id == source_id, WatchChangeRow.ts >= since
        )
        with self.session_factory() as session:
            return int(session.scalar(stmt) or 0)
