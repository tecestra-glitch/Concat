"""Content-relevance hashing and human-readable diffs between two adapter results.

A provider page changes on every request (nonces, timestamps, ads) but the *quotes* rarely do.
We therefore hash a canonical representation of the quotes only, and diff quote by quote:

* ``quote_change``  — buy/sell of an existing quote moved, or a quote appeared/disappeared;
* ``layout_change`` — the adapter went from OK to DEGRADED/ERROR, or the quote count fell by more
  than half (the page is probably still there but the parser no longer understands it);
* ``status_change`` — any other status transition (ok → blocked, error → ok, ok → stale ...).

The first observation of a source is a baseline: it never produces changes.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from ..adapters.base import AdapterResult, AdapterStatus, QuoteDraft
from .schemas import Change

LAYOUT_DROP_RATIO = 0.5  # quote count below 50 % of the previous poll -> layout_change
_FAILED_PARSE = {AdapterStatus.DEGRADED, AdapterStatus.ERROR}
_CONTEXT_ORDER = ("payment", "receive", "bank")


# --------------------------------------------------------------------------- canonical form
def dec_str(value: Decimal | None) -> str | None:
    """Stable decimal text: no exponent, no trailing zeros ("7350.00" -> "7350", "5.4043" stays)."""
    if value is None:
        return None
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _context_json(context: dict[str, Any] | None) -> str:
    if not context:
        return ""
    return json.dumps(context, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=False)


@dataclass(frozen=True, slots=True)
class QuoteKey:
    """Identity of a quote across polls: everything except the prices."""

    branch_id: str | None
    city: str | None
    base: str
    quote: str
    modality: str
    channel: str
    amount_base: str | None
    context: str  # canonical JSON ("" when none)

    def label(self) -> str:
        """Short human label: "USD/PYG CDE", "BRL/PYG transfer 5000 BRL pix→bank_account" ..."""
        parts = [f"{self.base}/{self.quote}"]
        if self.city:
            parts.append(self.city)
        if self.branch_id:
            parts.append(self.branch_id)
        if self.modality != "cash":
            parts.append(self.modality)
        if self.amount_base:
            parts.append(f"{self.amount_base} {self.base}")
        if self.context:
            ctx = json.loads(self.context)
            ordered = [str(ctx[k]) for k in _CONTEXT_ORDER if ctx.get(k) not in (None, "")]
            ordered += [f"{k}={v}" for k, v in sorted(ctx.items()) if k not in _CONTEXT_ORDER and v not in (None, "")]
            if ordered:
                parts.append("→".join(ordered[:2]) + (" " + " ".join(ordered[2:]) if len(ordered) > 2 else ""))
        return " ".join(parts)

    def as_dict(self) -> dict[str, Any]:
        return {
            "branch_id": self.branch_id,
            "city": self.city,
            "base": self.base,
            "quote": self.quote,
            "modality": self.modality,
            "channel": self.channel,
            "amount_base": self.amount_base,
            "context": json.loads(self.context) if self.context else None,
        }


@dataclass(frozen=True, slots=True)
class QuoteValue:
    buy: str | None
    sell: str | None

    def as_dict(self) -> dict[str, Any]:
        return {"buy": self.buy, "sell": self.sell}


CanonicalQuotes = dict[QuoteKey, QuoteValue]


def quote_key(q: QuoteDraft) -> QuoteKey:
    return QuoteKey(
        branch_id=q.branch_id,
        city=q.city,
        base=q.base,
        quote=q.quote,
        modality=q.modality,
        channel=q.channel,
        amount_base=dec_str(q.amount_base),
        context=_context_json(q.context),
    )


def canonical_quotes(result: AdapterResult | None) -> CanonicalQuotes:
    """Map key -> value. Duplicate keys keep the last occurrence (adapters should not emit them)."""
    if result is None:
        return {}
    return {quote_key(q): QuoteValue(dec_str(q.buy), dec_str(q.sell)) for q in result.quotes}


def canonical_rows(quotes: CanonicalQuotes) -> list[list[Any]]:
    """Sorted, JSON-friendly rows: the thing that gets hashed and persisted as snapshot."""
    rows = [
        [k.branch_id, k.city, k.base, k.quote, k.modality, k.channel, k.amount_base, k.context, v.buy, v.sell]
        for k, v in quotes.items()
    ]
    rows.sort(key=lambda r: tuple("" if x is None else str(x) for x in r))
    return rows


def rows_to_canonical(rows: list[list[Any]]) -> CanonicalQuotes:
    out: CanonicalQuotes = {}
    for r in rows:
        key = QuoteKey(r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7] or "")
        out[key] = QuoteValue(r[8], r[9])
    return out


def content_hash(result: AdapterResult | CanonicalQuotes | None) -> str:
    quotes = result if isinstance(result, dict) else canonical_quotes(result)
    payload = json.dumps(canonical_rows(quotes), separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- snapshots
@dataclass(slots=True)
class Snapshot:
    """What we remember about the previous poll of a source (persisted by the store)."""

    status: str  # AdapterStatus value
    quotes: CanonicalQuotes
    message: str | None = None

    @classmethod
    def from_result(cls, result: AdapterResult) -> Snapshot:
        return cls(status=str(result.status), quotes=canonical_quotes(result), message=result.message)

    def to_json(self) -> dict[str, Any]:
        return {"status": self.status, "message": self.message, "rows": canonical_rows(self.quotes)}

    @classmethod
    def from_json(cls, data: dict[str, Any] | None) -> Snapshot | None:
        if not data:
            return None
        return cls(
            status=str(data.get("status", "error")),
            quotes=rows_to_canonical(data.get("rows") or []),
            message=data.get("message"),
        )

    @property
    def hash(self) -> str:
        return content_hash(self.quotes)


# --------------------------------------------------------------------------- diff
def _fmt(value: str | None) -> str:
    return "—" if value is None else value


def _change(
    source_id: str, ts: datetime, kind: str, summary: str, before: dict[str, Any], after: dict[str, Any]
) -> Change:
    return Change(
        id=str(uuid.uuid4()), source_id=source_id, ts=ts, kind=kind, summary=summary, before=before, after=after
    )  # type: ignore[arg-type]


_FETCH_FAILED = {str(AdapterStatus.BLOCKED), str(AdapterStatus.ERROR), str(AdapterStatus.STALE)}


def is_layout_change(before: Snapshot, after: Snapshot) -> bool:
    before_status, after_status = before.status, after.status
    if before_status == AdapterStatus.OK and after_status in {str(s) for s in _FAILED_PARSE}:
        return True
    # Quote-count drop only signals layout change when the adapter actually parsed a page;
    # blocked/error/stale states produce 0 quotes because the fetch failed, not layout.
    if after_status in _FETCH_FAILED:
        return False
    n_before, n_after = len(before.quotes), len(after.quotes)
    return n_before > 0 and n_after < n_before * LAYOUT_DROP_RATIO


def diff_snapshots(
    before: Snapshot | None, after: Snapshot, *, source_id: str, ts: datetime | None = None
) -> list[Change]:
    """Changes between two snapshots, most significant first (layout, status, then quotes).

    `before is None` means first observation: no changes.
    """
    ts = ts or datetime.now(tz=UTC)
    if before is None:
        return []
    changes: list[Change] = []
    layout = is_layout_change(before, after)
    if layout:
        reason = after.message or "o parser deixou de reconhecer a página"
        summary = (
            f"layout mudou? cotações {len(before.quotes)} → {len(after.quotes)}, "
            f"status {before.status} → {after.status}: {reason}"
        )
        changes.append(
            _change(
                source_id,
                ts,
                "layout_change",
                summary,
                {"status": before.status, "quote_count": len(before.quotes)},
                {"status": after.status, "quote_count": len(after.quotes), "message": after.message},
            )
        )
    elif before.status != after.status:
        reason = f": {after.message}" if after.message else ""
        changes.append(
            _change(
                source_id,
                ts,
                "status_change",
                f"status {before.status} → {after.status}{reason}",
                {"status": before.status, "message": before.message},
                {"status": after.status, "message": after.message},
            )
        )
    if layout or not before.quotes or not after.quotes:
        # unreliable parse, or (re)establishing a baseline after an outage: no per-quote noise
        return changes
    changes.extend(diff_quotes(before.quotes, after.quotes, source_id=source_id, ts=ts))
    return changes


def diff_quotes(
    before: CanonicalQuotes, after: CanonicalQuotes, *, source_id: str, ts: datetime | None = None
) -> list[Change]:
    """One `quote_change` per quote whose buy/sell moved, appeared or disappeared."""
    ts = ts or datetime.now(tz=UTC)
    changes: list[Change] = []
    keys = sorted(set(before) | set(after), key=lambda k: k.label())
    for key in keys:
        old, new = before.get(key), after.get(key)
        if old == new:
            continue
        label = key.label()
        if old is None and new is not None:
            summary = f"{label} nova cotação: compra {_fmt(new.buy)} · venda {_fmt(new.sell)}"
        elif new is None and old is not None:
            summary = f"{label} cotação removida (era compra {_fmt(old.buy)} · venda {_fmt(old.sell)})"
        else:
            assert old is not None and new is not None
            moves = []
            if old.buy != new.buy:
                moves.append(f"compra {_fmt(old.buy)} → {_fmt(new.buy)}")
            if old.sell != new.sell:
                moves.append(f"venda {_fmt(old.sell)} → {_fmt(new.sell)}")
            summary = f"{label} " + ", ".join(moves)
        changes.append(
            _change(
                source_id,
                ts,
                "quote_change",
                summary,
                {"key": key.as_dict(), **(old.as_dict() if old else {"buy": None, "sell": None})},
                {"key": key.as_dict(), **(new.as_dict() if new else {"buy": None, "sell": None})},
            )
        )
    return changes


def diff_results(
    before: AdapterResult | None, after: AdapterResult, *, source_id: str, ts: datetime | None = None
) -> list[Change]:
    """Convenience wrapper over `diff_snapshots` for two raw adapter results."""
    return diff_snapshots(
        Snapshot.from_result(before) if before is not None else None,
        Snapshot.from_result(after),
        source_id=source_id,
        ts=ts,
    )
