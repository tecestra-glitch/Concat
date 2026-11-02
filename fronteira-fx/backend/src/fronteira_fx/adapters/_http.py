"""Shared helpers for adapters: HTTP fetching, hashing/evidence and number parsing.

Nothing here touches the database. `http_get`/`http_post` never raise for
provider-side failures: they return an `HttpOutcome` that can be turned into an
`AdapterResult` with `.failure(source_id)`.
"""
from __future__ import annotations

import hashlib
import re
import ssl
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Literal
from zoneinfo import ZoneInfo

import httpx

from .base import AdapterResult, AdapterStatus, EvidenceDraft

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)
DEFAULT_TIMEOUT = 20.0
EXCERPT_LIMIT = 2000

TZ_ASUNCION = ZoneInfo("America/Asuncion")
TZ_SAO_PAULO = ZoneInfo("America/Sao_Paulo")

LocaleHint = Literal["auto", "es_PY", "pt_BR", "en_US"]

ACCEPT_HTML = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
ACCEPT_JSON = "application/json, text/plain, */*"

# Phrases a WAF/anti-bot challenge page says. The bare word "captcha" is deliberately absent: legit pages
# embed reCAPTCHA (badge CSS, api.js loader, the v2 checkbox widget, gstatic styles) without being a challenge.
_BLOCK_MARKERS = (
    "cf-chl",
    "just a moment",
    "attention required",
    "checking your browser",
    "verify you are human",
    "verify that you are human",
    "complete the captcha",
    "solve the captcha",
    "access denied",
    "request unsuccessful. incapsula",
    "pardon our interruption",
)


def utcnow() -> datetime:
    return datetime.now(tz=UTC)


def default_headers(accept: str = ACCEPT_HTML, extra: dict[str, str] | None = None) -> dict[str, str]:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": accept,
        "Accept-Language": "es-PY,es;q=0.9,pt-BR;q=0.8,en;q=0.7",
    }
    if extra:
        headers.update(extra)
    return headers


# --------------------------------------------------------------------------- hashing / evidence
def sha256_hex(data: str | bytes) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8", errors="replace")
    return hashlib.sha256(data).hexdigest()


_WS = re.compile(r"\s+")
_TAGS = re.compile(r"<[^>]+>")


def excerpt(text: str | bytes, *, limit: int = EXCERPT_LIMIT, strip_tags: bool = False) -> str:
    """Collapse whitespace (optionally strip tags) and cut to `limit` chars."""
    if isinstance(text, bytes):
        text = text.decode("utf-8", errors="replace")
    if strip_tags:
        text = _TAGS.sub(" ", text)
    text = _WS.sub(" ", text).strip()
    if len(text) > limit:
        return text[: limit - 1] + "…"
    return text


def build_evidence(
    *,
    source_id: str,
    kind: Literal["html", "json", "screenshot", "manual"],
    url: str,
    captured_at: datetime,
    raw: str | bytes,
    rules: list[str],
    excerpt_text: str | None = None,
    raw_path: str | None = None,
) -> EvidenceDraft:
    return EvidenceDraft(
        source_id=source_id,
        kind=kind,
        url=url,
        captured_at=captured_at,
        sha256=sha256_hex(raw),
        excerpt=excerpt(excerpt_text if excerpt_text is not None else raw, strip_tags=kind == "html"),
        rules=rules,
        raw_path=raw_path,
    )


# --------------------------------------------------------------------------- numbers
_NUM_RE = re.compile(r"[-+]?\d[\d.,'  ]*")


def parse_decimal(text: str | int | float | Decimal, locale_hint: LocaleHint = "auto") -> Decimal:
    """Parse localized money text into a Decimal.

    Handles "7.350,00" -> 7350.00, "7,350" -> 7350 (auto/en_US) or 7.350 (es_PY/pt_BR),
    "7350" -> 7350, "5.4043" -> 5.4043, "Gs. 5.680" -> 5680, "1,234,567.89" -> 1234567.89.

    Rules: with both separators the last one is the decimal mark. With a single
    separator: en_US treats "," as thousands and "." as decimal; es_PY/pt_BR treat
    "," as decimal and "." as thousands when every group after it has 3 digits;
    "auto" treats either separator as thousands when every group after it has 3
    digits (so "7,350" and "7.350" both give 7350) and as decimal otherwise.
    Raises ValueError when no number is found.
    """
    if isinstance(text, Decimal):
        return text
    if isinstance(text, bool):  # bool is an int subclass; never money
        raise ValueError("boolean is not a number")
    if isinstance(text, int):
        return Decimal(text)
    if isinstance(text, float):
        return Decimal(repr(text))
    s = str(text).replace(" ", " ").replace(" ", " ")
    m = _NUM_RE.search(s)
    if not m:
        raise ValueError(f"no number in {text!r}")
    num = m.group(0).replace(" ", "").replace("'", "")
    sign = ""
    if num[0] in "+-":
        sign, num = ("-" if num[0] == "-" else ""), num[1:]
    num = num.strip(".,")
    if not num:
        raise ValueError(f"no digits in {text!r}")
    has_dot, has_comma = "." in num, "," in num
    if has_dot and has_comma:
        dec = "," if num.rfind(",") > num.rfind(".") else "."
        thou = "." if dec == "," else ","
        num = num.replace(thou, "").replace(dec, ".")
    elif has_dot or has_comma:
        sep = "." if has_dot else ","
        parts = num.split(sep)
        grouped = all(len(p) == 3 for p in parts[1:]) and 1 <= len(parts[0]) <= 3
        if locale_hint == "en_US":
            is_thousands = sep == ","
        elif locale_hint in ("es_PY", "pt_BR"):
            is_thousands = sep == "." and grouped
        else:
            is_thousands = grouped or len(parts) > 2
        if is_thousands:
            num = num.replace(sep, "")
        else:
            if len(parts) > 2:
                raise ValueError(f"ambiguous number {text!r}")
            num = num.replace(sep, ".")
    try:
        return Decimal(sign + num)
    except InvalidOperation as exc:  # pragma: no cover - defensive
        raise ValueError(f"invalid number {text!r}") from exc


def try_parse_decimal(text: Any, locale_hint: LocaleHint = "auto") -> Decimal | None:
    if text is None:
        return None
    try:
        return parse_decimal(text, locale_hint)
    except (ValueError, TypeError):
        return None


def positive_or_none(value: Decimal | None) -> Decimal | None:
    """Exchange houses publish 0 for currencies they do not trade: treat as missing."""
    if value is None or value <= 0:
        return None
    return value


# --------------------------------------------------------------------------- staleness
def is_stale(declared: datetime | None, captured_at: datetime, max_age: timedelta) -> bool:
    """True when the provider's declared timestamp is older than `max_age`.

    Naive datetimes are compared as UTC. A missing declared timestamp is never stale.
    """
    if declared is None:
        return False
    if declared.tzinfo is None:
        declared = declared.replace(tzinfo=UTC)
    if captured_at.tzinfo is None:
        captured_at = captured_at.replace(tzinfo=UTC)
    return captured_at - declared > max_age


# --------------------------------------------------------------------------- HTTP
@dataclass(slots=True)
class HttpOutcome:
    ok: bool
    status_code: int | None
    text: str
    url: str
    error: str | None = None
    blocked: bool = False
    tls_error: bool = False
    content: bytes = b""

    def failure(self, source_id: str, *, message: str | None = None) -> AdapterResult:  # noqa: ARG002
        status = AdapterStatus.BLOCKED if self.blocked else AdapterStatus.ERROR
        return AdapterResult(status=status, quotes=[], evidence=None, message=message or self.error or "http error")


def looks_blocked(status_code: int, text: str) -> bool:
    if status_code in (401, 403, 429):
        return True
    if status_code in (200, 503):
        head = text[:4000].lower()
        return any(marker in head for marker in _BLOCK_MARKERS)
    return False


def _classify_exception(exc: Exception, timeout: float) -> tuple[str, bool]:
    """Return (message, is_tls_error)."""
    if isinstance(exc, httpx.TimeoutException):
        return f"timeout after {timeout:g}s", False
    cause: BaseException | None = exc
    depth = 0
    while cause is not None and depth < 6:
        if isinstance(cause, ssl.SSLError) or "CERTIFICATE_VERIFY_FAILED" in str(cause):
            return f"TLS verification failed: {cause}", True
        cause = cause.__cause__ or cause.__context__
        depth += 1
    return f"{type(exc).__name__}: {exc}", False


async def http_request(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
    json: Any = None,
    timeout: float = DEFAULT_TIMEOUT,
    verify: bool | str | ssl.SSLContext = True,
    follow_redirects: bool = True,
    client: httpx.AsyncClient | None = None,
) -> HttpOutcome:
    """One request, no retries (the collector handles backoff)."""
    hdrs = default_headers() if headers is None else headers
    try:
        if client is None:
            async with httpx.AsyncClient(timeout=timeout, verify=verify, follow_redirects=follow_redirects) as c:
                resp = await c.request(method, url, headers=hdrs, params=params, data=data, json=json)
        else:
            resp = await client.request(method, url, headers=hdrs, params=params, data=data, json=json)
    except httpx.HTTPError as exc:
        message, tls = _classify_exception(exc, timeout)
        return HttpOutcome(ok=False, status_code=None, text="", url=url, error=message, tls_error=tls)
    except ssl.SSLError as exc:  # pragma: no cover - httpx normally wraps it
        return HttpOutcome(ok=False, status_code=None, text="", url=url,
                           error=f"TLS verification failed: {exc}", tls_error=True)
    text = resp.text
    final_url = str(resp.url)
    if looks_blocked(resp.status_code, text):
        return HttpOutcome(
            ok=False, status_code=resp.status_code, text=text, url=final_url,
            error=f"HTTP {resp.status_code}: blocked by anti-bot/WAF", blocked=True, content=resp.content,
        )
    if resp.status_code >= 400:
        return HttpOutcome(
            ok=False, status_code=resp.status_code, text=text, url=final_url,
            error=f"HTTP {resp.status_code}", content=resp.content,
        )
    return HttpOutcome(ok=True, status_code=resp.status_code, text=text, url=final_url, content=resp.content)


async def http_get(url: str, **kwargs: Any) -> HttpOutcome:
    return await http_request("GET", url, **kwargs)


async def http_post(url: str, **kwargs: Any) -> HttpOutcome:
    return await http_request("POST", url, **kwargs)
