"""Orchestrates one discovery run: guard -> throttle -> one browser visit -> ranking -> one plain-HTTP replay.

The report is a plain dict (JSON-ready). Nothing sensitive is kept: see redact.py. Candidates carry two
internal keys (`_url`, `_post_data`) used only by the replay and the scaffold; they are never serialised.
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

from .capture import Captured, CaptureResult, capture
from .redact import is_secret_param, scrub_params, scrub_text
from .scoring import score_text
from .urlguard import Resolver, UnsafeUrl, check_public_url

TOOL_VERSION = "0.1.0"
USER_AGENT = "FronteiraFX-fx-discover/0.1 (ferramenta local de desenvolvimento; sem login; uma visita por execucao)"
MIN_INTERVAL_S = 60.0
REPLAY_TIMEOUT_S = 20.0
TOP_N = 10
ANALYTICS_HOSTS = (
    "google-analytics.com", "googletagmanager.com", "doubleclick.net", "facebook.net", "facebook.com",
    "hotjar.com", "clarity.ms", "segment.io", "sentry.io", "newrelic.com", "nr-data.net", "criteo.com",
)
TEXTUAL = ("json", "html", "xml", "text/", "javascript", "x-www-form-urlencoded")


class ThrottleError(RuntimeError):
    """A visit to the same host happened less than MIN_INTERVAL_S ago."""


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def _load_state(state_file: Path) -> dict[str, float]:
    if not state_file.exists():
        return {}
    try:
        data = json.loads(state_file.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}
    return {str(k): float(v) for k, v in data.items()} if isinstance(data, dict) else {}


def check_throttle(state_file: Path, url: str, *, now: float | None = None) -> None:
    now = time.time() if now is None else now
    last = _load_state(state_file).get(_host(url))
    if last is not None and now - last < MIN_INTERVAL_S:
        raise ThrottleError(
            f"última visita a {_host(url)} há {now - last:.0f} s; aguarde {MIN_INTERVAL_S - (now - last):.0f} s"
        )


def record_visit(state_file: Path, url: str, *, now: float | None = None) -> None:
    now = time.time() if now is None else now
    state = _load_state(state_file)
    state[_host(url)] = now
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _is_textual(content_type: str | None) -> bool:
    return content_type is None or any(marker in content_type for marker in TEXTUAL)


def _safe_url(url: str) -> str:
    """Same URL with secret-looking query values replaced by a marker."""
    parts = urlsplit(url)
    if not parts.query:
        return url
    query = [(k, "<redigido>" if is_secret_param(k) else v) for k, v in parse_qsl(parts.query, keep_blank_values=True)]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query, safe="<>"), ""))


def _body_params(post_data: str | None) -> dict[str, str]:
    if not post_data:
        return {}
    if post_data.lstrip().startswith(("{", "[")):
        try:
            data = json.loads(post_data)
        except ValueError:
            return {}
        if not isinstance(data, dict):
            return {}
        return {str(k): (v if isinstance(v, str) else json.dumps(v))[:200] for k, v in data.items()}
    return dict(parse_qsl(post_data, keep_blank_values=True))


def skip_reason(rec: Captured) -> str | None:
    """Why a captured response is not a candidate (None when it is one)."""
    host = _host(rec.url)
    if any(host == h or host.endswith("." + h) for h in ANALYTICS_HOSTS):
        return "analytics"
    if not rec.body:
        return "sem corpo" + (f" ({rec.error})" if rec.error else "")
    if not _is_textual(rec.content_type):
        return "binario"
    return None


def skipped_summary(records: list[Captured]) -> list[str]:
    """Human notes on XHR/fetch responses that were dropped (counts per reason, no URLs)."""
    counts: dict[str, int] = {}
    for rec in records:
        if rec.resource_type not in ("xhr", "fetch"):
            continue
        reason = skip_reason(rec)
        if reason:
            key = reason.split(" (")[0]
            counts[key] = counts.get(key, 0) + 1
    if not counts:
        return []
    detail = ", ".join(f"{n} {k}" for k, n in sorted(counts.items()))
    return [f"respostas XHR/fetch descartadas: {detail}"]


def build_candidates(records: list[Captured]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for rec in records:
        if skip_reason(rec) is not None:
            continue
        text = rec.body.decode("utf-8", errors="replace")
        score = score_text(text, is_json=bool(rec.content_type and "json" in rec.content_type))
        out.append(
            {
                "method": rec.method,
                "url": _safe_url(rec.url),
                "resource_type": rec.resource_type,
                "status": rec.status,
                "content_type": rec.content_type,
                "size_bytes": len(rec.body),
                "body_truncated": rec.body_truncated,
                "score": score.total,
                "reasons": score.reasons,
                "query_params": scrub_params(dict(parse_qsl(urlsplit(rec.url).query, keep_blank_values=True))),
                "body_params": scrub_params(_body_params(rec.post_data)),
                "required_headers": rec.request_headers,
                "omitted_headers": rec.omitted_headers,
                "excerpt": scrub_text(text, limit=300),
                "sha256": hashlib.sha256(rec.body).hexdigest(),
                "_url": rec.url,
                "_post_data": rec.post_data,
                "_body": rec.body,
            }
        )
    out.sort(key=lambda c: (-c["score"], -c["size_bytes"]))
    for rank, cand in enumerate(out[:TOP_N], start=1):
        cand["rank"] = rank
    return out[:TOP_N]


def replay_once(candidate: dict[str, Any], *, resolver: Resolver | None = None,
                transport: httpx.BaseTransport | None = None) -> dict[str, Any]:
    """Repeat the candidate call once with plain httpx: no cookies, no browser. Never raises."""
    try:
        check_public_url(candidate["_url"], resolver=resolver)
    except UnsafeUrl as exc:
        return {"works_without_browser": False, "error": f"URL recusada: {exc}"}
    data = candidate.get("_post_data")
    # HTTP header values must be ASCII for httpx; values with accents are not replayed (their names are reported).
    headers = {k: v for k, v in candidate["required_headers"].items() if v.isascii()}
    dropped = sorted(k for k in candidate["required_headers"] if k not in headers)
    try:
        with httpx.Client(timeout=REPLAY_TIMEOUT_S, follow_redirects=False, transport=transport) as client:
            resp = client.request(candidate["method"], candidate["_url"], headers=headers,
                                  content=data.encode("utf-8") if data else None)
    except (httpx.HTTPError, UnicodeError, ValueError) as exc:
        return {"works_without_browser": False, "error": type(exc).__name__, "headers_not_replayed": dropped}
    body = resp.content
    content_type = (resp.headers.get("content-type") or "").split(";")[0].strip().lower() or None
    score = score_text(body.decode("utf-8", errors="replace"), is_json=bool(content_type and "json" in content_type))
    return {
        "works_without_browser": 200 <= resp.status_code < 300 and bool(body) and score.total > 0,
        "status": resp.status_code,
        "content_type": content_type,
        "size_bytes": len(body),
        "score": score.total,
        "headers_not_replayed": dropped,
    }


def _public_candidate(cand: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in cand.items() if not k.startswith("_")}


async def run_discovery(
    url: str,
    *,
    seconds: float = 20.0,
    state_file: Path | None = None,
    resolver: Resolver | None = None,
    replay_transport: httpx.BaseTransport | None = None,
    capture_fn: Any = None,
) -> dict[str, Any]:
    """One visit. Returns a JSON-ready report; `candidates_internal` (not serialised) keeps raw bodies."""
    check_public_url(url, resolver=resolver)
    if state_file is not None:
        check_throttle(state_file, url)
    seconds = max(5.0, min(float(seconds), 120.0))
    visit = capture_fn or capture
    if state_file is not None:
        record_visit(state_file, url)  # recorded before the visit: a failed visit still counts
    result: CaptureResult = await visit(url, seconds=seconds, user_agent=USER_AGENT)
    cands = build_candidates(result.records)
    notes: list[str] = skipped_summary(result.records)
    if not cands:
        notes.append("nenhuma resposta textual de XHR/fetch/documento com corpo; a página pode não expor API")
    else:
        replay = replay_once(cands[0], resolver=resolver, transport=replay_transport)
        cands[0]["replay"] = {k: v for k, v in replay.items()}
        notes.append(
            "replay sem navegador do candidato 1: "
            + ("funciona" if replay.get("works_without_browser") else "não funciona sem navegador")
        )
    if result.blocked_urls:
        notes.append(f"{result.blocked_urls} requisição(ões) do navegador bloqueadas por não serem públicas")
    report = {
        "tool": "fx-discover",
        "tool_version": TOOL_VERSION,
        "url": url,
        "final_url": scrub_text(result.final_url, limit=500),
        "title": scrub_text(result.title, limit=200),
        "captured_at": datetime.now(tz=UTC).isoformat(timespec="seconds"),
        "seconds": seconds,
        "user_agent": USER_AGENT,
        "requests_seen": result.requests_seen,
        "blocked_urls": result.blocked_urls,
        "candidates": [_public_candidate(c) for c in cands],
        "notes": notes,
        "candidates_internal": cands,
    }
    return report


def to_json_text(report: dict[str, Any]) -> str:
    public = {k: v for k, v in report.items() if k != "candidates_internal"}
    return json.dumps(public, indent=2, ensure_ascii=False) + "\n"
