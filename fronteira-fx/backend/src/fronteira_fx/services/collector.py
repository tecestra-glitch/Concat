"""Collector: runs provider adapters, stores quotes + evidence + events, detects changes (module `watch`),
evaluates alert rules (module `notify`) and schedules each source with an adaptive interval/backoff.

The adapter registry (`fronteira_fx.adapters.registry`) is owned by another module and imported lazily and
defensively: when it is missing the collector simply has no adapters.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from ..adapters.base import Adapter, AdapterInfo, AdapterResult, AdapterStatus
from ..config import Settings
from ..db import session_scope
from ..models import Branch, Evidence, Quote, Source, Task, utcnow
from ..schemas import ChangeOut
from . import alerts as alerts_svc
from . import events as events_svc
from . import watch as watch_svc
from .opportunities import opportunity_payload, recompute_opportunities
from .quotes import latest_quotes, quote_to_out, store_quote_draft

log = logging.getLogger("fronteira_fx.collector")

HEALTH_BY_STATUS: dict[AdapterStatus, str] = {
    AdapterStatus.OK: "ok",
    AdapterStatus.DEGRADED: "degraded",
    AdapterStatus.BLOCKED: "blocked",
    AdapterStatus.STALE: "stale",
    AdapterStatus.NEEDS_SESSION: "blocked",
    AdapterStatus.ERROR: "degraded",
}
FAILURE_STATUSES = {AdapterStatus.BLOCKED, AdapterStatus.NEEDS_SESSION, AdapterStatus.ERROR}


def load_registry() -> dict[str, Adapter]:
    try:
        from ..adapters.registry import ADAPTERS  # type: ignore[import-not-found]
    except Exception as exc:  # registry not ready yet or broken: run with no adapters
        log.warning("adapter registry unavailable: %s", exc)
        return {}
    return dict(ADAPTERS)


@dataclass(slots=True)
class CollectOutcome:
    source_id: str
    status: str  # adapter status value, or "skipped"
    health: str
    quotes_stored: int = 0
    new_capture: bool = True
    message: str | None = None
    evidence_id: str | None = None
    skipped: bool = False
    changes: list[ChangeOut] = field(default_factory=list)
    alert_event_ids: list[str] = field(default_factory=list)


def backoff_delay(interval_s: int, failures: int, max_s: int) -> timedelta:
    """Exponential backoff: interval * 2^(failures-1), capped."""
    if failures <= 0:
        return timedelta(seconds=interval_s)
    return timedelta(seconds=min(interval_s * (2 ** (failures - 1)), max_s))


class Collector:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        settings: Settings,
        *,
        adapters: Mapping[str, Adapter] | None = None,
        now_fn: Any = utcnow,
        inline_browser: bool = False,
    ) -> None:
        self.session_factory = session_factory
        self.settings = settings
        self._adapters = dict(adapters) if adapters is not None else None
        self.now_fn = now_fn
        self.inline_browser = inline_browser
        self._last_sha: dict[str, str] = {}
        self._last_evidence: dict[str, str] = {}
        self._known_opportunities: set[str] | None = None

    @property
    def data_mode(self) -> str:
        return self.settings.data_mode

    def adapters(self) -> dict[str, Adapter]:
        if self._adapters is None:
            self._adapters = load_registry()
        return self._adapters

    # -- sources -----------------------------------------------------------------------------
    def ensure_source(self, session: Session, info: AdapterInfo) -> Source:
        src = session.get(Source, info.id)
        if src is None:
            src = Source(id=info.id, data_mode=self.data_mode, health="unknown")
            session.add(src)
        elif src.data_mode != self.data_mode:
            raise ValueError(
                f"source {info.id!r} belongs to data_mode {src.data_mode!r}, collector runs {self.data_mode!r}"
            )
        src.name = info.name
        src.kind = info.kind
        src.method = info.method
        src.url = info.url
        src.capabilities = list(info.capabilities)
        src.limitations = list(info.limitations)
        src.coverage_cities = list(info.cities)
        src.coverage_currencies = list(info.currencies)
        src.poll_interval_s = info.poll_interval_s or self.settings.poll_interval_s
        session.flush()
        watch_svc.ensure_watch(
            session,
            src,
            now=self.now_fn(),
            data_mode=self.data_mode,
            min_interval_s=self.settings.watch_min_interval_s,
            max_interval_s=self.settings.watch_max_interval_s,
        )
        return src

    def ensure_sources(self) -> list[str]:
        ids = []
        with session_scope(self.session_factory) as session:
            for adapter in self.adapters().values():
                self.ensure_source(session, adapter.info)
                ids.append(adapter.info.id)
        return ids

    # -- ingestion ---------------------------------------------------------------------------
    def ingest(
        self, session: Session, info: AdapterInfo, result: AdapterResult, *, now: datetime | None = None
    ) -> CollectOutcome:
        now = now or self.now_fn()
        source = self.ensure_source(session, info)
        ws = watch_svc.ensure_watch(session, source, now=now, data_mode=self.data_mode)
        health = HEALTH_BY_STATUS.get(result.status, "unknown")
        previous_health = source.health
        previous_status = ws.status
        outcome = CollectOutcome(source_id=info.id, status=str(result.status), health=health, message=result.message)

        # evidence (cached by sha256: a re-captured identical page reuses the evidence row)
        evidence_id: str | None = None
        new_capture = True
        content_hash: str | None = None
        if result.evidence is not None:
            ev = result.evidence
            content_hash = ev.sha256
            if self._last_sha.get(info.id) == ev.sha256 and info.id in self._last_evidence:
                evidence_id = self._last_evidence[info.id]
                new_capture = False
            else:
                row = Evidence(
                    source_id=info.id,
                    kind=ev.kind,
                    url=ev.url,
                    captured_at=ev.captured_at,
                    sha256=ev.sha256,
                    excerpt=ev.excerpt[:2000],
                    rules=list(ev.rules),
                    raw_path=ev.raw_path,
                    data_mode=self.data_mode,
                )
                session.add(row)
                session.flush()
                evidence_id = row.id
                self._last_sha[info.id] = ev.sha256
                self._last_evidence[info.id] = row.id
        outcome.evidence_id = evidence_id
        outcome.new_capture = new_capture

        # quotes (+ change detection against the previous latest per context)
        previous = (
            latest_quotes(session, data_mode=self.data_mode, source=info.id, lookback_s=None) if result.quotes else []
        )
        stored_rows: list[Quote] = []
        for draft in result.quotes:
            if draft.branch_id and session.get(Branch, draft.branch_id) is None:
                session.add(
                    Branch(
                        id=draft.branch_id,
                        source_id=info.id,
                        name=draft.branch_id,
                        city=draft.city,
                        data_mode=self.data_mode,
                    )
                )
                session.flush()
            row = store_quote_draft(session, draft, evidence_id=evidence_id, data_mode=self.data_mode, captured_at=now)
            stored_rows.append(row)
            if new_capture:
                events_svc.append_event(
                    session,
                    "quote.updated",
                    quote_to_out(row).model_dump(mode="json"),
                    data_mode=self.data_mode,
                    ts=now,
                )
        outcome.quotes_stored = len(stored_rows)

        changes = []
        if new_capture and stored_rows:
            for summary, before, after in watch_svc.detect_quote_changes(previous, stored_rows):
                changes.append(
                    watch_svc.record_change(
                        session,
                        source_id=info.id,
                        kind="quote_change",
                        summary=summary,
                        before=before,
                        after=after,
                        evidence_id=evidence_id,
                        now=now,
                        data_mode=self.data_mode,
                    )
                )
        if result.status == AdapterStatus.DEGRADED and new_capture:
            changes.append(
                watch_svc.record_change(
                    session,
                    source_id=info.id,
                    kind="layout_change",
                    summary=result.message or "layout parcial / degradado",
                    before={"status": previous_status},
                    after={"status": str(result.status)},
                    evidence_id=evidence_id,
                    now=now,
                    data_mode=self.data_mode,
                )
            )
        if previous_status != str(result.status):
            changes.append(
                watch_svc.record_change(
                    session,
                    source_id=info.id,
                    kind="status_change",
                    summary=f"{info.id}: {previous_status} → {result.status}",
                    before={"status": previous_status},
                    after={"status": str(result.status), "message": result.message},
                    evidence_id=evidence_id,
                    now=now,
                    data_mode=self.data_mode,
                )
            )
        outcome.changes = [watch_svc.change_to_out(c) for c in changes]

        # health + schedule (adaptive interval / backoff live in the watch state; Source mirrors it)
        failed = result.status in FAILURE_STATUSES or (not result.quotes and result.status != AdapterStatus.OK)
        source.health = health
        if failed:
            source.consecutive_failures = (source.consecutive_failures or 0) + 1
            source.last_error = result.message or str(result.status)
        else:
            source.consecutive_failures = 0
            source.last_error = result.message if result.status != AdapterStatus.OK else None
            source.last_success_at = now
        real_changes = [c for c in changes if c.kind == "quote_change" and c.before]
        changed: bool | None = None if (not previous and not real_changes) else bool(real_changes) and new_capture
        watch_svc.after_run(
            ws,
            now=now,
            ok=not failed,
            changed=changed,
            status=str(result.status),
            content_hash=content_hash,
            backoff_max_s=self.settings.backoff_max_s,
        )
        if failed:  # classic exponential backoff on the Source schedule too
            ws.next_run_at = now + backoff_delay(
                source.poll_interval_s, source.consecutive_failures, self.settings.backoff_max_s
            )
        source.next_poll_at = ws.next_run_at
        source.updated_at = now
        if previous_health != health or failed:
            events_svc.append_event(
                session,
                "source.health",
                {
                    "source_id": info.id,
                    "health": health,
                    "last_error": source.last_error,
                    "consecutive_failures": source.consecutive_failures,
                    "next_poll_at": source.next_poll_at.isoformat(),
                },
                data_mode=self.data_mode,
                ts=now,
            )

        # opportunities + alerts
        opp_rows = []
        new_ids: set[str] = set()
        if stored_rows and new_capture:
            opp_rows = recompute_opportunities(session, data_mode=self.data_mode, now=now)
            ids = {o.id for o in opp_rows}
            if self._known_opportunities is not None:
                new_ids = ids - self._known_opportunities
            self._known_opportunities = ids
            events_svc.append_event(
                session, "opportunity.updated", opportunity_payload(opp_rows), data_mode=self.data_mode, ts=now
            )
        ctx = alerts_svc.AlertContext(
            now=now,
            source_id=info.id,
            health=health,
            previous_health=previous_health,
            changes=changes,
            opportunities=opp_rows,
            new_opportunity_ids=new_ids,
        )
        outcome.alert_event_ids = [e.id for e in alerts_svc.evaluate_rules(session, ctx, data_mode=self.data_mode)]
        session.flush()
        return outcome

    # -- collection --------------------------------------------------------------------------
    async def collect(
        self, adapter: Adapter, *, force: bool = False, params: Mapping[str, Any] | None = None
    ) -> CollectOutcome:
        info = adapter.info
        now = self.now_fn()
        with session_scope(self.session_factory) as session:
            source = self.ensure_source(session, info)
            ws = watch_svc.ensure_watch(session, source, now=now, data_mode=self.data_mode)
            if not force and not watch_svc.is_due(ws, now):
                reason = "desabilitada" if not ws.enabled else f"próxima sondagem {ws.next_run_at.isoformat()}"
                return CollectOutcome(
                    source_id=info.id, status="skipped", health=source.health, skipped=True, message=reason
                )
        try:
            result = await adapter.fetch(**dict(params or {}))
        except Exception as exc:  # adapters should not raise, but never let one kill the loop
            log.exception("adapter %s raised", info.id)
            result = AdapterResult(
                status=AdapterStatus.ERROR, quotes=[], evidence=None, message=f"{type(exc).__name__}: {exc}"
            )
        with session_scope(self.session_factory) as session:
            outcome = self.ingest(session, info, result, now=self.now_fn())
        if outcome.alert_event_ids:
            await alerts_svc.deliver_events(self.session_factory, outcome.alert_event_ids, self.settings)
        return outcome

    async def run_once(self, *, force: bool = False) -> list[CollectOutcome]:
        if self.data_mode != "real":
            return []  # demo instances never scrape providers
        outcomes = []
        for source_id in sorted(self.adapters()):
            outcomes.append(await self.collect(self.adapters()[source_id], force=force))
        return outcomes

    async def poll_now(self, source_id: str) -> ChangeOut | None:
        """`POST /v1/watch/run/{id}`: immediate poll; first detected Change or None. None also when unknown."""
        adapter = self.adapters().get(source_id)
        if adapter is None or self.data_mode != "real":
            return None
        outcome = await self.collect(adapter, force=True)
        return outcome.changes[0] if outcome.changes else None

    # -- on-demand requests ------------------------------------------------------------------
    def _latest_for(self, session: Session, source_id: str, params: Mapping[str, Any]) -> Quote | None:
        amount = params.get("amount") or params.get("amount_base")
        rows = latest_quotes(
            session,
            data_mode=self.data_mode,
            source=source_id,
            base=params.get("base"),
            quote=params.get("quote"),
            city=params.get("city"),
            modality=params.get("modality"),
            amount=Decimal(str(amount)) if amount is not None else None,
            lookback_s=None,
        )
        return rows[0] if rows else None

    async def request_quote(self, source_id: str, params: Mapping[str, Any]) -> dict[str, Any]:
        now = self.now_fn()
        if self.data_mode != "real":
            with session_scope(self.session_factory) as session:
                q = self._latest_for(session, source_id, params)
                if q is None:
                    return {"status": "blocked", "reason": f"fonte '{source_id}' sem cotação no modo {self.data_mode}"}
                return {"status": "done", "quote": quote_to_out(q)}

        adapter = self.adapters().get(source_id)
        if adapter is None:
            return {"status": "blocked", "reason": f"fonte '{source_id}' sem adaptador registrado"}
        with session_scope(self.session_factory) as session:
            source = self.ensure_source(session, adapter.info)
            if source.health == "blocked" and source.next_poll_at is not None and now < source.next_poll_at:
                return {"status": "blocked", "reason": source.last_error or "fonte bloqueada (backoff ativo)"}
            if adapter.info.method == "browser" and not self.inline_browser:
                task = Task(
                    source_id=source_id,
                    kind="fetch_quote",
                    params=dict(params),
                    status="queued",
                    data_mode=self.data_mode,
                    created_at=now,
                )
                session.add(task)
                session.flush()
                return {"status": "queued", "job_id": task.id, "reason": "requer navegador; o worker processa a fila"}

        outcome = await self.collect(adapter, force=True, params=params)
        if outcome.health == "blocked":
            return {"status": "blocked", "reason": outcome.message or "fonte bloqueada"}
        with session_scope(self.session_factory) as session:
            q = self._latest_for(session, source_id, params)
            if q is None or q.captured_at < now:
                reason = outcome.message or f"fonte respondeu {outcome.status} sem cotação para estes parâmetros"
                return {"status": "blocked", "reason": reason}
            return {"status": "done", "quote": quote_to_out(q)}

    async def process_tasks(self, limit: int = 10) -> int:
        if self.data_mode != "real":
            return 0
        with session_scope(self.session_factory) as session:
            tasks = list(
                session.scalars(
                    select(Task)
                    .where(Task.status == "queued", Task.data_mode == self.data_mode)
                    .order_by(Task.created_at.asc())
                    .limit(limit)
                )
            )
            todo = [(t.id, t.source_id, dict(t.params or {})) for t in tasks]
            for t in tasks:
                t.status = "running"
                t.started_at = self.now_fn()
        done = 0
        for task_id, source_id, params in todo:
            adapter = self.adapters().get(source_id or "")
            if adapter is None:
                outcome = CollectOutcome(
                    source_id=source_id or "", status="error", health="unknown", message="adaptador não registrado"
                )
            else:
                outcome = await self.collect(adapter, force=True, params=params)
            with session_scope(self.session_factory) as session:
                task = session.get(Task, task_id)
                if task is not None:
                    task.finished_at = self.now_fn()
                    failed = outcome.health in ("blocked", "unknown") and not outcome.quotes_stored
                    task.status = "failed" if failed else "done"
                    task.result = {
                        "status": outcome.status,
                        "health": outcome.health,
                        "quotes_stored": outcome.quotes_stored,
                        "evidence_id": outcome.evidence_id,
                    }
                    task.error = outcome.message if failed else None
            done += 1
        return done

    def prune_events(self) -> int:
        with session_scope(self.session_factory) as session:
            return events_svc.prune(
                session,
                max_events=self.settings.event_retention,
                max_age_s=self.settings.event_retention_s,
                now=self.now_fn(),
            )
