"""Adaptive per-source polling schedule. Pure logic: no I/O, clock and RNG are injected.

Rules (all tunable through `SchedulerConfig`):

* the interval starts at the adapter's ``poll_interval_s`` and always stays inside
  ``[min_interval_s, max_interval_s]`` (default 60 s .. 900 s) — never hammer a provider;
* after a *real* change the interval shrinks (× ``shorten_factor``, default 0.5);
* after ``unchanged_polls_before_lengthen`` polls without change it grows (× ``lengthen_factor``, 1.5);
* after an error the next run is delayed by an exponential backoff with jitter, capped at
  ``backoff_cap_s`` (30 min); a *blocked* answer starts one step further up the ladder;
* outside business hours (local time ``timezone``) the interval is multiplied by ``off_hours_factor``;
* a manual override (``interval_s``) freezes the interval (clamped to the minimum) and disables the
  adaptive/business-hours scaling; ``enabled=False`` stops the source; ``run_now`` makes it due.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

Clock = Callable[[], datetime]


def utcnow() -> datetime:
    return datetime.now(tz=UTC)


@dataclass(slots=True)
class SchedulerConfig:
    min_interval_s: int = 60
    max_interval_s: int = 900
    shorten_factor: float = 0.5
    lengthen_factor: float = 1.5
    unchanged_polls_before_lengthen: int = 3
    backoff_cap_s: int = 1800
    jitter: float = 0.15  # ±15 % on error backoff
    timezone: str = "America/Asuncion"
    business_hours: tuple[int, int] = (7, 20)  # local [start, end) hours
    business_days: frozenset[int] = frozenset({0, 1, 2, 3, 4, 5})  # Mon..Sat (CDE houses open Saturdays)
    off_hours_factor: float = 3.0

    def __post_init__(self) -> None:
        if self.min_interval_s < 1:
            raise ValueError("min_interval_s must be >= 1")
        if self.max_interval_s < self.min_interval_s:
            raise ValueError("max_interval_s must be >= min_interval_s")
        start, end = self.business_hours
        if not (0 <= start < end <= 24):
            raise ValueError("business_hours must satisfy 0 <= start < end <= 24")


@dataclass(slots=True)
class SourceSchedule:
    source_id: str
    base_interval_s: int
    interval_s: int
    min_interval_s: int
    max_interval_s: int
    enabled: bool = True
    manual_interval_s: int | None = None
    errors_in_row: int = 0
    unchanged_in_row: int = 0
    next_run_at: datetime | None = None
    last_run_at: datetime | None = None
    last_change_at: datetime | None = None
    running: bool = False
    run_now_requested: bool = False
    history: list[tuple[datetime, str]] = field(default_factory=list)  # last decisions, for debugging

    def clamp(self, value: float) -> int:
        return int(max(self.min_interval_s, min(self.max_interval_s, round(value))))


class Scheduler:
    def __init__(
        self,
        config: SchedulerConfig | None = None,
        *,
        clock: Clock = utcnow,
        rng: random.Random | None = None,
    ) -> None:
        self.config = config or SchedulerConfig()
        self.clock = clock
        self.rng = rng or random.Random()
        self._tz = ZoneInfo(self.config.timezone)
        self._sources: dict[str, SourceSchedule] = {}

    # ------------------------------------------------------------------ registry
    def add_source(
        self,
        source_id: str,
        poll_interval_s: int,
        *,
        min_interval_s: int | None = None,
        max_interval_s: int | None = None,
        enabled: bool = True,
        interval_s: int | None = None,
        manual_interval_s: int | None = None,
        first_run_at: datetime | None = None,
    ) -> SourceSchedule:
        """Register (or re-register) a source. New sources are due immediately unless `first_run_at` is given."""
        lo = max(1, min_interval_s if min_interval_s is not None else self.config.min_interval_s)
        hi = max(lo, max_interval_s if max_interval_s is not None else self.config.max_interval_s)
        sched = SourceSchedule(
            source_id=source_id,
            base_interval_s=poll_interval_s,
            interval_s=0,
            min_interval_s=lo,
            max_interval_s=hi,
            enabled=enabled,
        )
        sched.interval_s = sched.clamp(interval_s if interval_s is not None else poll_interval_s)
        if manual_interval_s is not None:
            sched.manual_interval_s = max(lo, int(manual_interval_s))
            sched.interval_s = sched.manual_interval_s
        now = self.clock()
        sched.next_run_at = (first_run_at or now) if enabled else None
        self._sources[source_id] = sched
        return sched

    def remove_source(self, source_id: str) -> None:
        self._sources.pop(source_id, None)

    def get(self, source_id: str) -> SourceSchedule:
        try:
            return self._sources[source_id]
        except KeyError:
            raise KeyError(f"unknown watch source {source_id!r}") from None

    def __contains__(self, source_id: object) -> bool:
        return source_id in self._sources

    def sources(self) -> list[SourceSchedule]:
        return [self._sources[k] for k in sorted(self._sources)]

    # ------------------------------------------------------------------ queries
    def is_business_hours(self, now: datetime | None = None) -> bool:
        now = now or self.clock()
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        local = now.astimezone(self._tz)
        start, end = self.config.business_hours
        return local.weekday() in self.config.business_days and start <= local.hour < end

    def effective_interval(self, source_id: str, now: datetime | None = None) -> int:
        """Interval that will be used for the next regular wait (business-hours aware)."""
        s = self.get(source_id)
        if s.manual_interval_s is not None:
            return s.manual_interval_s
        if self.is_business_hours(now):
            return s.interval_s
        return int(
            max(
                s.min_interval_s,
                min(
                    s.max_interval_s * self.config.off_hours_factor, round(s.interval_s * self.config.off_hours_factor)
                ),
            )
        )

    def due(self, now: datetime | None = None) -> list[str]:
        """Ids of enabled, idle sources whose `next_run_at` has passed, earliest first."""
        now = now or self.clock()
        ready = [
            s
            for s in self._sources.values()
            if (s.enabled or s.run_now_requested)
            and not s.running
            and s.next_run_at is not None
            and s.next_run_at <= now
        ]
        ready.sort(key=lambda s: (not s.run_now_requested, s.next_run_at or now, s.source_id))
        return [s.source_id for s in ready]

    def next_wakeup(self, now: datetime | None = None) -> datetime | None:
        """Earliest `next_run_at` among enabled, idle sources (None when nothing is scheduled)."""
        candidates = [
            s.next_run_at for s in self._sources.values() if s.enabled and not s.running and s.next_run_at is not None
        ]
        return min(candidates) if candidates else None

    # ------------------------------------------------------------------ transitions
    def mark_started(self, source_id: str, now: datetime | None = None) -> None:
        s = self.get(source_id)
        s.running = True
        s.run_now_requested = False
        s.last_run_at = now or self.clock()

    def record_result(
        self,
        source_id: str,
        *,
        changed: bool,
        error: bool = False,
        blocked: bool = False,
        now: datetime | None = None,
    ) -> SourceSchedule:
        """Apply the outcome of one poll and compute `next_run_at`."""
        s = self.get(source_id)
        now = now or self.clock()
        s.running = False
        s.last_run_at = now
        if error or blocked:
            s.errors_in_row += 1
            s.unchanged_in_row = 0
            exponent = s.errors_in_row + (1 if blocked else 0)
            base = s.manual_interval_s if s.manual_interval_s is not None else s.interval_s
            delay = min(self.config.backoff_cap_s, base * (2**exponent))
            delay = max(s.min_interval_s, delay * self.rng.uniform(1 - self.config.jitter, 1 + self.config.jitter))
            s.next_run_at = now + timedelta(seconds=delay)
            s.history.append((now, f"{'blocked' if blocked else 'error'} #{s.errors_in_row}: retry in {delay:.0f}s"))
        else:
            s.errors_in_row = 0
            if changed:
                s.last_change_at = now
                s.unchanged_in_row = 0
                if s.manual_interval_s is None:
                    s.interval_s = s.clamp(s.interval_s * self.config.shorten_factor)
                s.history.append((now, f"changed: interval {s.interval_s}s"))
            else:
                s.unchanged_in_row += 1
                if s.unchanged_in_row >= self.config.unchanged_polls_before_lengthen:
                    s.unchanged_in_row = 0
                    if s.manual_interval_s is None:
                        s.interval_s = s.clamp(s.interval_s * self.config.lengthen_factor)
                    s.history.append((now, f"quiet: interval {s.interval_s}s"))
            wait = self.effective_interval(source_id, now)
            s.next_run_at = now + timedelta(seconds=wait)
        if not s.enabled:
            s.next_run_at = None
        del s.history[:-20]
        return s

    def override(
        self,
        source_id: str,
        *,
        interval_s: int | None = None,
        enabled: bool | None = None,
        now: datetime | None = None,
    ) -> SourceSchedule:
        """Manual adjustment. `interval_s` fixes the interval (clamped to the minimum); `enabled` toggles."""
        s = self.get(source_id)
        now = now or self.clock()
        if interval_s is not None:
            s.manual_interval_s = max(s.min_interval_s, int(interval_s))
            s.interval_s = s.manual_interval_s
            s.unchanged_in_row = 0
            if s.enabled and s.next_run_at is not None:
                anchor = s.last_run_at or now
                s.next_run_at = max(now, anchor + timedelta(seconds=s.manual_interval_s))
            s.history.append((now, f"manual interval {s.manual_interval_s}s"))
        if enabled is not None and enabled != s.enabled:
            s.enabled = enabled
            if enabled:
                s.errors_in_row = 0
                s.next_run_at = now
                s.history.append((now, "enabled"))
            else:
                s.next_run_at = None
                s.run_now_requested = False
                s.history.append((now, "disabled"))
        return s

    def clear_override(self, source_id: str) -> SourceSchedule:
        s = self.get(source_id)
        s.manual_interval_s = None
        s.interval_s = s.clamp(s.base_interval_s)
        return s

    def run_now(self, source_id: str, now: datetime | None = None) -> SourceSchedule:
        """Make the source due immediately (even when disabled: a manual poll is always allowed once)."""
        s = self.get(source_id)
        s.next_run_at = now or self.clock()
        s.run_now_requested = True
        return s
