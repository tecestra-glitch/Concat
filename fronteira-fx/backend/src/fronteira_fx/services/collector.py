"""Collector: runs provider adapters, stores quotes + evidence + events, detects changes (module `watch`),
evaluates alert rules (module `notify`) and schedules each source with an adaptive interval/backoff.

The adapter registry (`fronteira_fx.adapters.registry`) is owned by another module and imported lazily and
defensively: when it is missing the collector simply has no adapters.
"""

from __future__ import annotations

import logging
import math
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, sessionmaker

from ..adapters.base import Adapter, AdapterInfo, AdapterResult, AdapterStatus
from ..config import Settings
from ..db import session_scope
from ..models import Branch, Evidence, Quote, Source, Task, utcnow
from ..schemas import ChangeOut
from ..watch.fetcher import FetchOutcome, conditional_get
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
FORCE_FLOOR_S = 60  # a source is never fetched twice within this window, forced or not (D6)


class CollectorError(Exception):
    """Base class for the typed collector errors the API maps to HTTP statuses (D4/D6)."""


class UnknownSource(CollectorError):
    def __init__(self, source_id: str) -> None:
        super().__init__(f"fonte '{source_id}' sem adaptador registrado")
        self.source_id = source_id


class WrongDataMode(CollectorError):
    def __init__(self, data_mode: str) -> None:
        super().__init__(f"sondagem indisponível no modo {data_mode}; só o modo real consulta provedores")
        self.data_mode = data_mode


class RateLimited(CollectorError):
    def __init__(self, source_id: str, retry_after_s: int) -> None:
        super().__init__(
            f"fonte '{source_id}' sondada há menos de {FORCE_FLOOR_S} s; tente novamente em {retry_after_s} s"
        )
        self.source_id = source_id
        self.retry_after_s = retry_after_s


def load_registry() -> dict[str, Adapter]:
    try:
        from ..adapters.registry import active_adapters  # type: ignore[import-not-found]
    except Exception as exc:  # registry not ready yet or broken: run with no adapters
        log.warning("adapter registry unavailable: %s", exc)
        return {}
    return active_adapters()


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
    retry_after_s: int | None = None  # set when a forced run fell inside the 60 s floor (D6)
    changes: list[ChangeOut] = field(default_factory=list)
    alert_event_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SkippedSource:
    source_id: str
    reason: str  # our own wording only: never a third-party message or body


@dataclass(slots=True)
class RoundResult:
    """One round of the worker's loop, for a caller that cannot keep a process alive (serverless)."""

    data_mode: str
    outcomes: list[CollectOutcome] = field(default_factory=list)  # sources fetched in this round (304 included)
    skipped: list[SkippedSource] = field(default_factory=list)
    tasks_processed: int = 0
    events_pruned: int = 0
    budget_exhausted: bool = False


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
        self._last_outcome: dict[str, CollectOutcome] = {}
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
        src.integration = info.integration
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
        self,
        session: Session,
        info: AdapterInfo,
        result: AdapterResult,
        *,
        now: datetime | None = None,
        etag: str | None = None,
        last_modified: str | None = None,
    ) -> CollectOutcome:
        """Store one adapter result. `etag`/`last_modified` are the validators of the HTTP response the
        collector itself made (conditional GET); adapters that fetch on their own leave them None."""
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
        # Only content that parsed OK may be revalidated: a 304 skips the parser, so a validator kept after a failed
        # or partial parse would hide a parser fix until the site changes. Otherwise the watch forgets them.
        revalidate = result.status == AdapterStatus.OK
        watch_svc.after_run(
            ws,
            now=now,
            ok=not failed,
            changed=changed,
            status=str(result.status),
            content_hash=content_hash,
            etag=etag if revalidate else None,
            last_modified=last_modified if revalidate else None,
            backoff_max_s=self.settings.backoff_max_s,
        )
        if not revalidate:
            ws.etag = None
            ws.last_modified = None
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
            cycles=alerts_svc.cycles_for_rules(session, data_mode=self.data_mode),
        )
        outcome.alert_event_ids = [e.id for e in alerts_svc.evaluate_rules(session, ctx, data_mode=self.data_mode)]
        session.flush()
        return outcome

    # -- collection --------------------------------------------------------------------------
    def _uses_remote_browser(self, adapter: Adapter) -> bool:
        """A browser adapter that opted in runs on the mini navegador when it is configured (no local Chromium)."""
        return (
            adapter.info.method == "browser"
            and bool(getattr(adapter, "remote_browser", False))
            and self.settings.remote_browser_enabled
        )

    def _floor_remaining_s(self, ws: Any, now: datetime, extra_floor_s: int = 0) -> int | None:
        """Seconds left in the per-source floor (D6), or None when a fetch is allowed.

        `extra_floor_s` raises the floor for sources that cost a remote browser run (remote_browser_min_interval_s).
        """
        if ws.last_run_at is None:
            return None
        floor = max(FORCE_FLOOR_S, int(ws.min_interval_s or 0), int(extra_floor_s))
        remaining = (ws.last_run_at + timedelta(seconds=floor) - now).total_seconds()
        if remaining <= 0:
            return None
        return max(1, math.ceil(remaining))

    def _rate_limited_outcome(self, source_id: str, ws: Any, health: str, retry_after_s: int) -> CollectOutcome:
        last = self._last_outcome.get(source_id)
        if last is None:  # process restarted since the last run: rebuild the gist from the watch state
            last = CollectOutcome(source_id=source_id, status=ws.status, health=health, new_capture=False)
        return replace(last, skipped=True, retry_after_s=retry_after_s, changes=[], alert_event_ids=[])

    # -- conditional GET (B8/B9) --------------------------------------------------------------
    @staticmethod
    def _conditional_url(adapter: Adapter) -> str:
        """The single document the collector polls conditionally: `conditional_url` when the adapter declares
        one (e.g. a JSON endpoint behind a home page), otherwise `info.url`."""
        return getattr(adapter, "conditional_url", None) or adapter.info.url

    @staticmethod
    def _uses_conditional_get(adapter: Adapter, params: Mapping[str, Any] | None) -> bool:
        """Scheduled polls of adapters that opt in (`conditional_get = True`) are fetched by the collector
        with If-None-Match / If-Modified-Since; the adapter only parses. On-demand requests with parameters
        always go through the adapter's own `fetch` (forms, amounts, sessions)."""
        return (
            bool(getattr(adapter, "conditional_get", False))
            and params is None
            and bool(Collector._conditional_url(adapter))
        )

    def _store_raw(self, source_id: str, fetched: FetchOutcome, *, now: datetime, sha256: str) -> str | None:
        """Write the raw payload under `settings.evidence_dir/<source>/`; never fails the collection."""
        payload = fetched.content if fetched.content is not None else (fetched.body or "").encode()
        if not payload:
            return None
        directory = Path(self.settings.evidence_dir) / source_id
        path = directory / f"{now.strftime('%Y%m%dT%H%M%SZ')}-{sha256[:12]}.html"
        try:
            directory.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
        except OSError as exc:
            log.warning("raw payload for %s not stored (%s): %s", source_id, path, exc)
            return None
        return str(path)

    def _parse_fetched(self, adapter: Adapter, fetched: FetchOutcome, *, now: datetime) -> AdapterResult:
        info = adapter.info
        if fetched.blocked:
            return AdapterResult(status=AdapterStatus.BLOCKED, quotes=[], evidence=None, message=fetched.error)
        if fetched.error is not None or fetched.body is None:
            message = fetched.error or f"HTTP {fetched.status_code}: resposta sem corpo"
            return AdapterResult(status=AdapterStatus.ERROR, quotes=[], evidence=None, message=message)
        try:
            result = adapter.parse(fetched.body, captured_at=now, url=fetched.url)
        except Exception as exc:  # a broken parser is a degraded source, not a dead worker
            log.exception("adapter %s parse raised", info.id)
            return AdapterResult(
                status=AdapterStatus.ERROR, quotes=[], evidence=None, message=f"{type(exc).__name__}: {exc}"
            )
        ev = result.evidence
        if ev is not None and ev.raw_path is None:
            raw_path = self._store_raw(info.id, fetched, now=now, sha256=ev.sha256)
            if raw_path is not None:
                result = replace(result, evidence=replace(ev, raw_path=raw_path))
        return result

    def _record_not_modified(self, info: AdapterInfo, fetched: FetchOutcome) -> CollectOutcome:
        """304: nothing to parse or diff; the page is unchanged, so the interval grows like an unchanged capture."""
        now = self.now_fn()
        with session_scope(self.session_factory) as session:
            source = self.ensure_source(session, info)
            ws = watch_svc.ensure_watch(session, source, now=now, data_mode=self.data_mode)
            watch_svc.after_run(
                ws,
                now=now,
                ok=True,
                changed=False,
                status=ws.status,
                content_hash=None,
                etag=fetched.etag,
                last_modified=fetched.last_modified,
                backoff_max_s=self.settings.backoff_max_s,
            )
            source.next_poll_at = ws.next_run_at
            source.updated_at = now
            outcome = CollectOutcome(
                source_id=info.id,
                status="not_modified",
                health=source.health,
                new_capture=False,
                message="304 Not Modified",
            )
        self._last_outcome[info.id] = outcome
        return outcome

    async def collect(
        self, adapter: Adapter, *, force: bool = False, params: Mapping[str, Any] | None = None
    ) -> CollectOutcome:
        info = adapter.info
        now = self.now_fn()
        with session_scope(self.session_factory) as session:
            source = self.ensure_source(session, info)
            ws = watch_svc.ensure_watch(session, source, now=now, data_mode=self.data_mode)
            # Row lock on Postgres (no-op on SQLite): the api and the worker check and reserve one at a time.
            session.refresh(ws, with_for_update=True)
            if not force and not watch_svc.is_due(ws, now):
                reason = "desabilitada" if not ws.enabled else f"próxima sondagem {ws.next_run_at.isoformat()}"
                return CollectOutcome(
                    source_id=info.id, status="skipped", health=source.health, skipped=True, message=reason
                )
            remote = self._uses_remote_browser(adapter)
            remaining = self._floor_remaining_s(
                ws, now, self.settings.remote_browser_min_interval_s if remote else 0
            )
            if remaining is not None:  # D6: never hammer a source, even on demand; hand back the last result
                return self._rate_limited_outcome(info.id, ws, source.health, remaining)
            # SEC-03: reserve the slot in the same transaction as the check, before any await, so callers that
            # arrive while this fetch is in flight (same process or another one) see the floor and get 429.
            ws.last_run_at = now
            validators = (ws.etag, ws.last_modified)
        fetched: FetchOutcome | None = None
        if self._uses_conditional_get(adapter, params):
            fetched = await conditional_get(
                self._conditional_url(adapter),
                etag=validators[0],
                last_modified=validators[1],
                headers=dict(getattr(adapter, "conditional_headers", None) or {}) or None,
            )
            if fetched.not_modified:
                return self._record_not_modified(info, fetched)
            result = self._parse_fetched(adapter, fetched, now=self.now_fn())
        else:
            try:
                result = await adapter.fetch(**dict(params or {}))
            except Exception as exc:  # adapters should not raise, but never let one kill the loop
                log.exception("adapter %s raised", info.id)
                result = AdapterResult(
                    status=AdapterStatus.ERROR, quotes=[], evidence=None, message=f"{type(exc).__name__}: {exc}"
                )
        with session_scope(self.session_factory) as session:
            outcome = self.ingest(
                session,
                info,
                result,
                now=self.now_fn(),
                etag=fetched.etag if fetched is not None else None,
                last_modified=fetched.last_modified if fetched is not None else None,
            )
        self._last_outcome[info.id] = outcome
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
        """`POST /v1/watch/run/{id}`: immediate poll; the first detected Change, or None when nothing changed.
        Raises UnknownSource (404), WrongDataMode (409) or RateLimited (429) instead of guessing (D4/D6)."""
        adapter = self.adapters().get(source_id)
        if adapter is None:
            raise UnknownSource(source_id)
        if self.data_mode != "real":
            raise WrongDataMode(self.data_mode)
        outcome = await self.collect(adapter, force=True)
        if outcome.retry_after_s is not None:
            raise RateLimited(source_id, outcome.retry_after_s)
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
            # the worker queue is only for a local Chromium; with the mini navegador the request runs here
            if adapter.info.method == "browser" and not self.inline_browser and not self._uses_remote_browser(adapter):
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
        if outcome.retry_after_s is not None:
            raise RateLimited(source_id, outcome.retry_after_s)
        if outcome.health == "blocked":
            return {"status": "blocked", "reason": outcome.message or "fonte bloqueada"}
        with session_scope(self.session_factory) as session:
            q = self._latest_for(session, source_id, params)
            if q is None or q.captured_at < now:
                reason = outcome.message or f"fonte respondeu {outcome.status} sem cotação para estes parâmetros"
                return {"status": "blocked", "reason": reason}
            return {"status": "done", "quote": quote_to_out(q)}

    def browser_source_ids(self) -> set[str]:
        return {sid for sid, adapter in self.adapters().items() if adapter.info.method == "browser"}

    async def process_tasks(
        self,
        limit: int = 10,
        *,
        skip_browser: bool = False,
        may_start: Callable[[], bool] | None = None,
    ) -> int:
        """Run queued on-demand tasks. `skip_browser` leaves browser-source tasks queued (no browser here);
        `may_start` is checked before each task, and the tasks not started go back to the queue."""
        if self.data_mode != "real":
            return 0
        excluded = self.browser_source_ids() if skip_browser else set()
        with session_scope(self.session_factory) as session:
            query = select(Task).where(Task.status == "queued", Task.data_mode == self.data_mode)
            if excluded:
                query = query.where(or_(Task.source_id.is_(None), Task.source_id.not_in(excluded)))
            tasks = list(session.scalars(query.order_by(Task.created_at.asc()).limit(limit)))
            todo = [(t.id, t.source_id, dict(t.params or {})) for t in tasks]
            for t in tasks:
                t.status = "running"
                t.started_at = self.now_fn()
        done = 0
        for index, (task_id, source_id, params) in enumerate(todo):
            if may_start is not None and not may_start():
                self._requeue_tasks([task_id for task_id, _, _ in todo[index:]])
                break
            adapter = self.adapters().get(source_id or "")
            if adapter is None:
                outcome = CollectOutcome(
                    source_id=source_id or "", status="error", health="unknown", message="adaptador não registrado"
                )
            else:
                outcome = await self.collect(adapter, force=True, params=params)
            with session_scope(self.session_factory) as session:
                task = session.get(Task, task_id)
                if task is None:
                    continue
                if outcome.retry_after_s is not None:  # inside the floor: back to the queue, next tick retries
                    task.status = "queued"
                    task.started_at = None  # it is waiting again, not "running since"
                    task.error = f"piso de {FORCE_FLOOR_S} s; nova tentativa em {outcome.retry_after_s} s"
                    continue
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

    def _requeue_tasks(self, task_ids: list[str]) -> None:
        with session_scope(self.session_factory) as session:
            for task in session.scalars(select(Task).where(Task.id.in_(task_ids))):
                task.status = "queued"
                task.started_at = None

    async def run_round(self, *, budget_s: float, clock: Callable[[], float] = time.monotonic) -> RoundResult:
        """One pass of the worker's loop without a worker: due sources (never forced), queued tasks without
        browser sources, and event pruning. No new source or task is started once `budget_s` has elapsed.
        Browser adapters are reported as skipped (they need the worker) unless the mini navegador is configured."""
        result = RoundResult(data_mode=self.data_mode)
        if self.data_mode != "real":
            return result  # demo and simulation instances never scrape providers (same rule as run_once)
        deadline = clock() + budget_s
        adapters = self.adapters()
        for source_id in sorted(adapters):
            adapter = adapters[source_id]
            if adapter.info.method == "browser" and not self._uses_remote_browser(adapter):
                result.skipped.append(SkippedSource(source_id, "requer navegador; só o worker coleta essa fonte"))
                continue
            if clock() >= deadline:
                result.budget_exhausted = True
                result.skipped.append(SkippedSource(source_id, "orçamento de tempo da rodada esgotado"))
                continue
            try:
                outcome = await self.collect(adapter)
            except Exception as exc:  # one source failing to store (e.g. a constraint) must not sink the round
                log.exception("source %s failed during the serverless round", source_id)
                result.skipped.append(SkippedSource(source_id, f"erro ao coletar ou gravar: {type(exc).__name__}"))
                continue
            if outcome.retry_after_s is not None:
                result.skipped.append(
                    SkippedSource(
                        source_id, f"sondada há pouco; piso de {FORCE_FLOOR_S} s (tente em {outcome.retry_after_s} s)"
                    )
                )
            elif outcome.skipped:
                result.skipped.append(SkippedSource(source_id, outcome.message or "não vencida"))
            else:
                result.outcomes.append(outcome)
        result.tasks_processed = await self.process_tasks(skip_browser=True, may_start=lambda: clock() < deadline)
        if clock() >= deadline:
            result.budget_exhausted = True
        result.events_pruned = self.prune_events()
        return result

    def prune_events(self) -> int:
        with session_scope(self.session_factory) as session:
            return events_svc.prune(
                session,
                max_events=self.settings.event_retention,
                max_age_s=self.settings.event_retention_s,
                now=self.now_fn(),
            )
