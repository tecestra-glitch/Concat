"""Small shared building blocks: branch metadata, city mapping, result helpers."""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta

from ._http import is_stale
from .base import AdapterResult, AdapterStatus, City, EvidenceDraft, QuoteDraft

# Only the three cities the terminal tracks get a code; everything else is None
# (the branch keeps its name, so nothing is lost, it is just not city-filterable).
_CITY_PATTERNS: tuple[tuple[str, City], ...] = (
    ("ciudad del este", "CDE"),
    ("ciudaddeleste", "CDE"),
    ("cde", "CDE"),
    ("asuncion", "ASU"),
    ("asu", "ASU"),
    ("villamorra", "ASU"),
    ("villa morra", "ASU"),
    ("pedro juan caballero", "PJC"),
    ("pedro juan", "PJC"),
    ("pjc", "PJC"),
    ("encarnacion", "ENC"),
    ("enc", "ENC"),
)


def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def city_from_text(text: str | None) -> City:
    """Map a branch/city label to CDE/ASU/PJC, else None."""
    if not text:
        return None
    norm = strip_accents(text).lower()
    tokens = set(norm.replace("-", " ").replace("_", " ").replace(".", " ").split())
    for pattern, city in _CITY_PATTERNS:
        if " " in pattern or len(pattern) > 3:
            if pattern in norm:
                return city
        elif pattern in tokens:
            return city
    return None


@dataclass(slots=True, frozen=True)
class BranchInfo:
    id: str                 # stable id, e.g. "chaco-9"
    name: str               # provider label
    city: City
    remote_code: str        # id used by the provider (API id, URL key, Livewire id...)
    address: str | None = None


def finalize(
    *,
    quotes: list[QuoteDraft],
    evidence: EvidenceDraft | None,
    issues: list[str],
    captured_at: datetime,
    stale_after: timedelta,
    degraded: bool = False,
    notes: list[str] | None = None,
    empty_message: str = "no quotes parsed (layout changed?)",
) -> AdapterResult:
    """Common status policy.

    - no quotes            -> ERROR (never silent zeros)
    - declared ts too old  -> STALE (quotes kept, so the collector can store them as stale)
    - partial / drift      -> DEGRADED
    - otherwise            -> OK (notes, if any, are carried in `message` without degrading)
    """
    notes = notes or []
    message = "; ".join([*issues, *notes]) or None
    if not quotes:
        return AdapterResult(status=AdapterStatus.ERROR, quotes=[], evidence=evidence, message=message or empty_message)
    declared = [q.declared_updated_at for q in quotes if q.declared_updated_at is not None]
    newest = max(declared) if declared else None
    if newest is not None and is_stale(newest, captured_at, stale_after):
        age = captured_at - (newest if newest.tzinfo else newest.replace(tzinfo=captured_at.tzinfo))
        stale_msg = f"declared update {newest.isoformat()} is {age.total_seconds() / 3600:.1f}h old"
        return AdapterResult(status=AdapterStatus.STALE, quotes=quotes, evidence=evidence,
                             message="; ".join([stale_msg, *issues, *notes]))
    if degraded or issues:
        return AdapterResult(status=AdapterStatus.DEGRADED, quotes=quotes, evidence=evidence, message=message)
    return AdapterResult(status=AdapterStatus.OK, quotes=quotes, evidence=evidence, message=message)


def error_result(message: str, evidence: EvidenceDraft | None = None) -> AdapterResult:
    return AdapterResult(status=AdapterStatus.ERROR, quotes=[], evidence=evidence, message=message)


def payload_kind(raw: str | bytes) -> str:
    """'json', 'html' or 'empty' from the first meaningful character."""
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    head = raw.lstrip()[:1]
    if not head:
        return "empty"
    if head in "{[":
        return "json"
    return "html"


def as_text(raw: str | bytes) -> str:
    return raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw


def quotes_excerpt(quotes: list[QuoteDraft], *, header: str = "") -> str:
    """Human-readable proof lines for EvidenceDraft.excerpt."""
    lines = [header] if header else []
    for q in quotes:
        declared = q.declared_updated_at.isoformat() if q.declared_updated_at else "-"
        ctx = f" ctx={q.context}" if q.context else ""
        lines.append(
            f"{q.branch_id or q.source_id} city={q.city or '-'} {q.base}/{q.quote} "
            f"buy={q.buy} sell={q.sell} {q.modality}/{q.kind} declared={declared}{ctx}"
        )
    return "\n".join(lines)


def slug(text: str) -> str:
    norm = strip_accents(text).lower()
    out = "".join(c if c.isalnum() else "-" for c in norm)
    while "--" in out:
        out = out.replace("--", "-")
    return out.strip("-")
