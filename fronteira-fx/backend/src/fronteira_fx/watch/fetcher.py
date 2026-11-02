"""Conditional HTTP GET for provider pages (ETag / If-None-Match, Last-Modified / If-Modified-Since).

A `304 Not Modified` costs the provider almost nothing and tells us the page did not change, so the
poller can skip parsing and diffing. The fetcher never raises for provider-side problems: timeouts,
connection errors, 4xx/5xx and anti-bot walls all come back as a `FetchOutcome` with `error` set.
"""

from __future__ import annotations

import ssl
import time
from dataclasses import dataclass

import httpx

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)
ACCEPT_HTML = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
DEFAULT_TIMEOUT_S = 20.0
MAX_BODY_BYTES = 5_000_000  # a rate board is a few hundred KB at most; bigger is not a rate board

_BLOCK_MARKERS = (
    "cf-chl",
    "just a moment",
    "attention required",
    "captcha",
    "access denied",
    "request unsuccessful. incapsula",
    "pardon our interruption",
)


@dataclass(slots=True)
class FetchOutcome:
    url: str
    status_code: int | None
    body: str | None
    etag: str | None
    last_modified: str | None
    not_modified: bool
    elapsed_ms: int
    error: str | None
    blocked: bool = False
    content: bytes | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and (self.not_modified or self.body is not None)


def default_headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": ACCEPT_HTML,
        "Accept-Language": "es-PY,es;q=0.9,pt-BR;q=0.8,en;q=0.7",
        "Cache-Control": "max-age=0",
    }
    if extra:
        headers.update(extra)
    return headers


def conditional_headers(etag: str | None, last_modified: str | None) -> dict[str, str]:
    headers: dict[str, str] = {}
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified
    return headers


def looks_blocked(status_code: int, text: str) -> bool:
    if status_code in (401, 403, 429):
        return True
    if status_code in (200, 503):
        head = text[:4000].lower()
        return any(marker in head for marker in _BLOCK_MARKERS)
    return False


def _describe(exc: Exception, timeout: float) -> str:
    if isinstance(exc, httpx.TimeoutException):
        return f"timeout after {timeout:g}s"
    cause: BaseException | None = exc
    for _ in range(6):
        if cause is None:
            break
        if isinstance(cause, ssl.SSLError) or "CERTIFICATE_VERIFY_FAILED" in str(cause):
            return f"TLS verification failed: {cause}"
        cause = cause.__cause__ or cause.__context__
    return f"{type(exc).__name__}: {exc}"


async def conditional_get(
    url: str,
    *,
    etag: str | None = None,
    last_modified: str | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT_S,
    client: httpx.AsyncClient | None = None,
    follow_redirects: bool = True,
) -> FetchOutcome:
    """One GET with validators. `etag`/`last_modified` are the values from the previous response.

    On 304 the outcome has `not_modified=True`, `body=None` and keeps the previous validators (or the
    ones the server echoed). On anti-bot responses `blocked=True`. Never raises for provider errors.
    """
    hdrs = default_headers(headers)
    hdrs.update(conditional_headers(etag, last_modified))
    started = time.perf_counter()

    def elapsed() -> int:
        return int((time.perf_counter() - started) * 1000)

    try:
        if client is None:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=follow_redirects) as c:
                resp = await c.get(url, headers=hdrs)
        else:
            resp = await client.get(url, headers=hdrs)
    except httpx.HTTPError as exc:
        return FetchOutcome(
            url=url,
            status_code=None,
            body=None,
            etag=etag,
            last_modified=last_modified,
            not_modified=False,
            elapsed_ms=elapsed(),
            error=_describe(exc, timeout),
        )
    except ssl.SSLError as exc:  # pragma: no cover - httpx normally wraps it
        return FetchOutcome(
            url=url,
            status_code=None,
            body=None,
            etag=etag,
            last_modified=last_modified,
            not_modified=False,
            elapsed_ms=elapsed(),
            error=f"TLS verification failed: {exc}",
        )

    final_url = str(resp.url)
    new_etag = resp.headers.get("ETag") or etag
    new_lm = resp.headers.get("Last-Modified") or last_modified
    if resp.status_code == 304:
        return FetchOutcome(
            url=final_url,
            status_code=304,
            body=None,
            etag=new_etag,
            last_modified=new_lm,
            not_modified=True,
            elapsed_ms=elapsed(),
            error=None,
        )
    content = resp.content
    if len(content) > MAX_BODY_BYTES:
        return FetchOutcome(
            url=final_url,
            status_code=resp.status_code,
            body=None,
            etag=etag,
            last_modified=last_modified,
            not_modified=False,
            elapsed_ms=elapsed(),
            error=f"body too large ({len(content)} bytes)",
        )
    text = resp.text
    if looks_blocked(resp.status_code, text):
        return FetchOutcome(
            url=final_url,
            status_code=resp.status_code,
            body=None,
            etag=etag,
            last_modified=last_modified,
            not_modified=False,
            elapsed_ms=elapsed(),
            error=f"HTTP {resp.status_code}: blocked by anti-bot/WAF",
            blocked=True,
            content=content,
        )
    if resp.status_code >= 400:
        return FetchOutcome(
            url=final_url,
            status_code=resp.status_code,
            body=None,
            etag=etag,
            last_modified=last_modified,
            not_modified=False,
            elapsed_ms=elapsed(),
            error=f"HTTP {resp.status_code}",
            content=content,
        )
    return FetchOutcome(
        url=final_url,
        status_code=resp.status_code,
        body=text,
        etag=new_etag,
        last_modified=new_lm,
        not_modified=False,
        elapsed_ms=elapsed(),
        error=None,
        content=content,
    )
