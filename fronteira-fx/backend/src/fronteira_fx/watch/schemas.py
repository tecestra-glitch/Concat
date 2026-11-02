"""Public shapes of the watch module (mirror of docs/api-contract.md, section "módulo watch").

Money travels as decimal strings; dates are timezone-aware UTC datetimes.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

WatchStatusValue = Literal["ok", "degraded", "blocked", "stale", "error", "needs_session"]
ChangeKind = Literal["quote_change", "layout_change", "status_change"]
FetchMode = Literal["conditional_get", "adapter_fetch", "disabled"]


class WatchStatus(BaseModel):
    """Live monitoring state of one source (what `GET /v1/watch/sources` returns)."""

    source_id: str
    enabled: bool = True
    interval_s: int
    min_interval_s: int
    max_interval_s: int
    next_run_at: datetime | None = None
    last_run_at: datetime | None = None
    last_change_at: datetime | None = None
    changes_24h: int = 0
    errors_in_row: int = 0
    etag: str | None = None
    content_hash: str | None = None
    status: WatchStatusValue = "stale"  # a source never polled is "stale" until its first poll
    # additive fields (not in the contract table; the frontend may ignore them)
    last_modified: str | None = None
    last_error: str | None = None
    interval_override_s: int | None = None
    mode: FetchMode = "adapter_fetch"


class Change(BaseModel):
    """A detected change (what `GET /v1/watch/changes` returns and `source.change` carries)."""

    id: str
    source_id: str
    ts: datetime
    kind: ChangeKind
    summary: str
    before: dict[str, Any] = Field(default_factory=dict)
    after: dict[str, Any] = Field(default_factory=dict)
    evidence_id: str | None = None


class WatchUpdate(BaseModel):
    """Body of `POST /v1/watch/sources/{id}`: manual override of the schedule."""

    interval_s: int | None = Field(default=None, ge=1, description="Fixed interval in seconds (clamped to min)")
    enabled: bool | None = None
