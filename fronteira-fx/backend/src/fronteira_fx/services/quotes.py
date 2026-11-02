"""Quotes: storing adapter drafts and reading the latest quote per comparable context."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..adapters.base import QuoteDraft
from ..decimal_utils import fmt
from ..models import Quote, utcnow
from ..schemas import FeeOut, QuoteOut


def context_hash(context: dict[str, Any] | None) -> str:
    if not context:
        return ""
    canonical = json.dumps(context, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def series_key(
    source_id: str,
    city: str | None,
    base: str,
    quote: str,
    modality: str,
    *,
    branch_id: str | None = None,
    amount_base: Decimal | None = None,
    ctx_hash: str = "",
) -> str:
    """Comparable context key, e.g. `chaco:CDE:USD/PYG:cash` (+ `:@branch`, `:amount`, `:ctx`)."""
    key = f"{source_id}:{city or 'digital'}:{base}/{quote}:{modality}"
    if branch_id:
        key += f":@{branch_id}"
    if amount_base is not None:
        key += f":{fmt(amount_base)}"
    if ctx_hash:
        key += f":{ctx_hash[:8]}"
    return key


def is_reference(q: Quote) -> bool:
    """Reference rates (BCP, PTAX...) are for valuation only: never an executable leg (B23)."""
    return q.kind == "market_reference" or q.modality == "reference"


def fees_to_json(fees: list[Any]) -> list[dict[str, Any]]:
    """Stored fee rows: `label`/`amount`/`currency`, plus `pct` (share of the input) when the adapter gives one."""
    out = []
    for f in fees:
        amount = getattr(f, "amount", None) if not isinstance(f, dict) else f.get("amount")
        pct = getattr(f, "pct", None) if not isinstance(f, dict) else f.get("pct")
        row: dict[str, Any] = {
            "label": f["label"] if isinstance(f, dict) else f.label,
            "amount": fmt(Decimal(str(amount))) if amount is not None else None,
            "currency": f["currency"] if isinstance(f, dict) else f.currency,
        }
        if pct is not None:
            row["pct"] = fmt(Decimal(str(pct)))
        out.append(row)
    return out


def store_quote_draft(
    session: Session,
    draft: QuoteDraft,
    *,
    evidence_id: str | None,
    data_mode: str,
    captured_at: datetime | None = None,
) -> Quote:
    captured_at = captured_at or utcnow()
    ctx_hash = context_hash(draft.context)
    row = Quote(
        source_id=draft.source_id,
        branch_id=draft.branch_id,
        city=draft.city,
        base=draft.base,
        quote=draft.quote,
        buy=draft.buy,
        sell=draft.sell,
        unit_note=draft.unit_note or f"{draft.quote} por 1 {draft.base}",
        amount_base=draft.amount_base,
        modality=draft.modality,
        kind=draft.kind,
        channel=draft.channel,
        context=draft.context,
        context_hash=ctx_hash,
        series_key=series_key(
            draft.source_id,
            draft.city,
            draft.base,
            draft.quote,
            draft.modality,
            branch_id=draft.branch_id,
            amount_base=draft.amount_base,
            ctx_hash=ctx_hash,
        ),
        fees=fees_to_json(draft.fees),
        captured_at=captured_at,
        declared_updated_at=draft.declared_updated_at,
        valid_until=draft.valid_until,
        evidence_id=evidence_id,
        data_mode=data_mode,
    )
    session.add(row)
    session.flush()
    return row


def context_identity(q: Quote) -> tuple:
    return (q.source_id, q.branch_id, q.base, q.quote, q.modality, fmt(q.amount_base), q.context_hash)


def latest_quotes(
    session: Session,
    *,
    data_mode: str,
    city: str | None = None,
    base: str | None = None,
    quote: str | None = None,
    source: str | None = None,
    modality: str | None = None,
    amount: Decimal | None = None,
    channel: str | None = None,
    since: datetime | None = None,
    lookback_s: int | None = 7 * 86400,
) -> list[Quote]:
    """Most recent quote per comparable context (source, branch, pair, modality, amount, context)."""
    stmt = select(Quote).where(Quote.data_mode == data_mode)
    if city:
        stmt = stmt.where(Quote.city == city)
    if base:
        stmt = stmt.where(Quote.base == base)
    if quote:
        stmt = stmt.where(Quote.quote == quote)
    if source:
        stmt = stmt.where(Quote.source_id == source)
    if modality:
        stmt = stmt.where(Quote.modality == modality)
    if channel:
        stmt = stmt.where(Quote.channel == channel)
    if since is None and lookback_s:
        since = utcnow() - timedelta(seconds=lookback_s)
    if since is not None:
        stmt = stmt.where(Quote.captured_at >= since)
    stmt = stmt.order_by(Quote.captured_at.desc(), Quote.id.desc())

    seen: set[tuple] = set()
    out: list[Quote] = []
    for q in session.scalars(stmt):
        if amount is not None and q.amount_base is not None and q.amount_base != amount:
            continue
        ident = context_identity(q)
        if ident in seen:
            continue
        seen.add(ident)
        out.append(q)
    out.sort(key=lambda q: (q.source_id, q.city or "", q.base, q.quote, q.modality, fmt(q.amount_base) or ""))
    return out


def quote_to_out(q: Quote) -> QuoteOut:
    return QuoteOut(
        id=q.id,
        source_id=q.source_id,
        branch_id=q.branch_id,
        city=q.city,
        base=q.base,
        quote=q.quote,
        buy=q.buy,
        sell=q.sell,
        unit_note=q.unit_note,
        amount_base=q.amount_base,
        modality=q.modality,
        kind=q.kind,
        channel=q.channel,
        context=q.context,
        fees=[FeeOut(**f) for f in (q.fees or [])],
        captured_at=q.captured_at,
        declared_updated_at=q.declared_updated_at,
        valid_until=q.valid_until,
        evidence_id=q.evidence_id,
        data_mode=q.data_mode,
        series_key=q.series_key,
    )
