"""Keeps the discovery report free of cookies, credentials and personal data.

Rules: Cookie/Authorization-like headers are never written (only their names are listed as omitted, so the
developer knows the browser needed them); query/body parameters whose names look like secrets keep only the
name; excerpts are truncated and scrubbed of e-mails, long digit runs (CPF/CNPJ/phone/card) and token-like values.
"""

from __future__ import annotations

import re

# Headers that identify a session or a person: never reported, never replayed.
_SECRET_HEADER_NAMES = {"cookie", "set-cookie", "authorization", "proxy-authorization"}
_SECRET_HEADER_HINTS = ("token", "csrf", "xsrf", "session", "secret", "api-key", "apikey", "auth")
# Headers that only describe the transport; the replay client sets them itself.
_TRANSPORT_HEADERS = {"host", "content-length", "connection", "accept-encoding", "te", "upgrade", "expect"}
_SECRET_PARAM_HINTS = ("token", "csrf", "xsrf", "session", "secret", "key", "auth", "sig", "password", "senha")

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_LONG_DIGITS = re.compile(r"(?<!\d)\d(?:[\d .-]{8,}\d)(?!\d)")
_JWT = re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{4,}")
_SECRET_KV = re.compile(
    r'(?i)("?(?:[\w-]*(?:token|secret|password|senha|cpf|cnpj|email|e-mail|telefone|phone|session)[\w-]*)"?\s*[:=]\s*)'
    r'("[^"]*"|[^\s,}&]+)'
)
_WS = re.compile(r"\s+")


def is_secret_header(name: str) -> bool:
    low = name.lower()
    return low in _SECRET_HEADER_NAMES or any(h in low for h in _SECRET_HEADER_HINTS)


def split_headers(headers: dict[str, str]) -> tuple[dict[str, str], list[str]]:
    """(headers safe to replay and to report, names of headers omitted for being secret)."""
    kept: dict[str, str] = {}
    omitted: list[str] = []
    for name, value in headers.items():
        low = name.lower()
        if low in _TRANSPORT_HEADERS or low.startswith(":"):
            continue
        if is_secret_header(low):
            omitted.append(low)
            continue
        kept[low] = value
    return kept, sorted(set(omitted))


def is_secret_param(name: str) -> bool:
    low = name.lower()
    return any(h in low for h in _SECRET_PARAM_HINTS)


def scrub_params(params: dict[str, str]) -> dict[str, str]:
    """Secret-looking parameters keep their name and lose the value."""
    return {k: ("<redigido>" if is_secret_param(k) else scrub_text(v, limit=200)) for k, v in params.items()}


def scrub_raw(text: str) -> str:
    """Scrub a payload kept as a test fixture: same substitutions, whitespace and structure preserved."""
    text = _JWT.sub("<token>", text)
    text = _EMAIL.sub("<email>", text)
    text = _LONG_DIGITS.sub("<numero>", text)
    return _SECRET_KV.sub(lambda m: m.group(1) + "<redigido>", text)


def scrub_text(text: str, *, limit: int = 300) -> str:
    text = _JWT.sub("<token>", text)
    text = _EMAIL.sub("<email>", text)
    text = _LONG_DIGITS.sub("<numero>", text)
    text = _SECRET_KV.sub(lambda m: m.group(1) + "<redigido>", text)
    text = _WS.sub(" ", text).strip()
    if len(text) > limit:
        text = text[: limit - 1] + "…"
    return text
