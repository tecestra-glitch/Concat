"""SQLAlchemy 2.0 typed models. Works on SQLite (dev/tests) and PostgreSQL + pgvector (compose).

Money columns use `Money` (Numeric(24,8) on Postgres, canonical decimal strings on SQLite) so
values stay exact everywhere. Every business row carries `data_mode` ("real" | "demo").
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    TypeDecorator,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from .decimal_utils import fmt

EMBEDDING_DIM = 1536


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return str(uuid.uuid4())


class Money(TypeDecorator[Decimal]):
    """Exact decimal storage on every backend."""

    impl = Numeric(24, 8)
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> Any:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(Numeric(24, 8, asdecimal=True))
        return dialect.type_descriptor(String(64))

    def process_bind_param(self, value: Any, dialect: Dialect) -> Any:
        if value is None:
            return None
        dec = value if isinstance(value, Decimal) else Decimal(str(value))
        if dialect.name == "postgresql":
            return dec
        return fmt(dec, None)

    def process_result_value(self, value: Any, dialect: Dialect) -> Decimal | None:
        if value is None:
            return None
        return value if isinstance(value, Decimal) else Decimal(str(value))


class UTCDateTime(TypeDecorator[datetime]):
    """Store naive UTC, return aware UTC (SQLite drops tzinfo)."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Dialect) -> Any:
        if value is None:
            return None
        if value.tzinfo is not None:
            value = value.astimezone(UTC)
        if dialect.name == "postgresql":
            return value if value.tzinfo else value.replace(tzinfo=UTC)
        return value.replace(tzinfo=None)

    def process_result_value(self, value: Any, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


class EmbeddingVector(TypeDecorator[list[float]]):
    """pgvector `Vector(dim)` on PostgreSQL, JSON list on other backends."""

    impl = JSON
    cache_ok = True

    def __init__(self, dim: int = EMBEDDING_DIM) -> None:
        super().__init__()
        self.dim = dim

    def load_dialect_impl(self, dialect: Dialect) -> Any:
        if dialect.name == "postgresql":
            from pgvector.sqlalchemy import Vector

            return dialect.type_descriptor(Vector(self.dim))
        return dialect.type_descriptor(JSON())

    def process_bind_param(self, value: Any, dialect: Dialect) -> Any:
        if value is None:
            return None
        return [float(x) for x in value]

    def process_result_value(self, value: Any, dialect: Dialect) -> list[float] | None:
        if value is None:
            return None
        return [float(x) for x in value]


JSONType = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: JSONType, list[Any]: JSONType}


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(32))
    method: Mapped[str] = mapped_column(String(32))
    url: Mapped[str] = mapped_column(Text, default="")
    health: Mapped[str] = mapped_column(String(16), default="unknown")
    last_success_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    capabilities: Mapped[list[Any]] = mapped_column(JSONType, default=list)
    limitations: Mapped[list[Any]] = mapped_column(JSONType, default=list)
    coverage_cities: Mapped[list[Any]] = mapped_column(JSONType, default=list)
    coverage_currencies: Mapped[list[Any]] = mapped_column(JSONType, default=list)
    poll_interval_s: Mapped[int] = mapped_column(Integer, default=300)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    next_poll_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    data_mode: Mapped[str] = mapped_column(String(16), default="real", index=True)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    branches: Mapped[list[Branch]] = relationship(back_populates="source", cascade="all, delete-orphan")


class Branch(Base):
    __tablename__ = "branches"

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    city: Mapped[str | None] = mapped_column(String(8), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_mode: Mapped[str] = mapped_column(String(16), default="real", index=True)

    source: Mapped[Source] = relationship(back_populates="branches")


class Evidence(Base):
    __tablename__ = "evidence"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16))
    url: Mapped[str] = mapped_column(Text, default="")
    captured_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    sha256: Mapped[str] = mapped_column(String(64), default="")
    excerpt: Mapped[str] = mapped_column(Text, default="")
    rules: Mapped[list[Any]] = mapped_column(JSONType, default=list)
    raw_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_mode: Mapped[str] = mapped_column(String(16), default="real", index=True)


class Quote(Base):
    __tablename__ = "quotes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    branch_id: Mapped[str | None] = mapped_column(ForeignKey("branches.id", ondelete="SET NULL"), nullable=True)
    city: Mapped[str | None] = mapped_column(String(8), nullable=True, index=True)
    base: Mapped[str] = mapped_column(String(3))
    quote: Mapped[str] = mapped_column(String(3))
    buy: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    sell: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    unit_note: Mapped[str] = mapped_column(String(64), default="")
    amount_base: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    modality: Mapped[str] = mapped_column(String(16))
    kind: Mapped[str] = mapped_column(String(24))
    channel: Mapped[str] = mapped_column(String(16))
    context: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
    context_hash: Mapped[str] = mapped_column(String(64), default="")
    series_key: Mapped[str] = mapped_column(String(255), index=True)
    fees: Mapped[list[Any]] = mapped_column(JSONType, default=list)
    captured_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    declared_updated_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    valid_until: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    evidence_id: Mapped[str | None] = mapped_column(ForeignKey("evidence.id", ondelete="SET NULL"), nullable=True)
    data_mode: Mapped[str] = mapped_column(String(16), default="real", index=True)

    __table_args__ = (
        Index(
            "uq_quotes_context_capture",
            "source_id",
            "branch_id",
            "base",
            "quote",
            "modality",
            "amount_base",
            "context_hash",
            "captured_at",
            unique=True,
        ),
        Index("ix_quotes_series_captured", "series_key", "captured_at"),
    )


class QuoteEvent(Base):
    """Append-only event stream; `id` doubles as the SSE cursor."""

    __tablename__ = "quote_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(String(64), index=True)
    ts: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    data_mode: Mapped[str] = mapped_column(String(16), default="real", index=True)


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    institution: Mapped[str] = mapped_column(String(64))
    label: Mapped[str] = mapped_column(String(200))
    currency: Mapped[str] = mapped_column(String(3))
    kind: Mapped[str] = mapped_column(String(16))
    location: Mapped[str] = mapped_column(String(16), default="digital")
    balance_free: Mapped[Decimal] = mapped_column(Money, default=Decimal(0))
    balance_reserved: Mapped[Decimal] = mapped_column(Money, default=Decimal(0))
    balance_in_transit: Mapped[Decimal] = mapped_column(Money, default=Decimal(0))
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)
    data_mode: Mapped[str] = mapped_column(String(16), default="real", index=True)


class Position(Base):
    __tablename__ = "positions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    account_id: Mapped[str | None] = mapped_column(ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True)
    currency: Mapped[str] = mapped_column(String(3))
    location: Mapped[str] = mapped_column(String(16), default="digital")
    modality: Mapped[str] = mapped_column(String(16), default="account")
    amount: Mapped[Decimal] = mapped_column(Money, default=Decimal(0))
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)
    data_mode: Mapped[str] = mapped_column(String(16), default="real", index=True)


class Simulation(Base):
    __tablename__ = "simulations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    objective: Mapped[str] = mapped_column(String(16))
    capital_brl: Mapped[Decimal] = mapped_column(Money)
    request: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    result: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    data_mode: Mapped[str] = mapped_column(String(16), default="real", index=True)


class Opportunity(Base):
    __tablename__ = "opportunities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(300))
    kind: Mapped[str] = mapped_column(String(24))
    channel: Mapped[str] = mapped_column(String(16))
    city: Mapped[str | None] = mapped_column(String(8), nullable=True)
    objective: Mapped[str] = mapped_column(String(16), default="cycle")
    capital_brl: Mapped[Decimal] = mapped_column(Money)
    final_value_brl: Mapped[Decimal] = mapped_column(Money)
    net_gain_brl: Mapped[Decimal] = mapped_column(Money)
    roi: Mapped[Decimal] = mapped_column(Money)
    effective_rate: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    valuation_currency: Mapped[str] = mapped_column(String(3), default="BRL")
    steps: Mapped[list[Any]] = mapped_column(JSONType, default=list)
    confidence: Mapped[str] = mapped_column(String(16))
    pending_costs: Mapped[list[Any]] = mapped_column(JSONType, default=list)
    in_main_ranking: Mapped[bool] = mapped_column(Boolean, default=False)
    ranking_reason: Mapped[str] = mapped_column(Text, default="")
    comparable_best_digital_roi: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    computed_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    simulation_id: Mapped[str | None] = mapped_column(ForeignKey("simulations.id", ondelete="SET NULL"), nullable=True)
    data_mode: Mapped[str] = mapped_column(String(16), default="real", index=True)


class JournalEntry(Base):
    __tablename__ = "journal_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    ts: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    kind: Mapped[str] = mapped_column(String(16), default="note")
    text: Mapped[str] = mapped_column(Text, default="")
    amounts: Mapped[list[Any]] = mapped_column(JSONType, default=list)
    account_ids: Mapped[list[Any]] = mapped_column(JSONType, default=list)
    data_mode: Mapped[str] = mapped_column(String(16), default="real", index=True)


class Document(Base):
    """RAG corpus: evidence excerpts, parser notes, provider docs."""

    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_id: Mapped[str | None] = mapped_column(ForeignKey("sources.id", ondelete="SET NULL"), nullable=True)
    source: Mapped[str | None] = mapped_column(String(200), nullable=True)  # free text: "ueno docs", URL...
    title: Mapped[str | None] = mapped_column(String(300), nullable=True)
    text: Mapped[str] = mapped_column(Text)
    tags: Mapped[list[Any]] = mapped_column(JSONType, default=list)
    meta: Mapped[dict[str, Any]] = mapped_column("metadata", JSONType, default=dict)
    embedding: Mapped[list[float] | None] = mapped_column(EmbeddingVector(EMBEDDING_DIM), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    data_mode: Mapped[str] = mapped_column(String(16), default="real", index=True)

    chunks: Mapped[list[DocumentChunk]] = relationship(back_populates="document", cascade="all, delete-orphan")


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    ord: Mapped[int] = mapped_column(Integer, default=0)
    text: Mapped[str] = mapped_column(Text)
    tokens: Mapped[list[Any]] = mapped_column(JSONType, default=list)  # normalised terms for lexical search
    embedding: Mapped[list[float] | None] = mapped_column(EmbeddingVector(EMBEDDING_DIM), nullable=True)
    data_mode: Mapped[str] = mapped_column(String(16), default="real", index=True)

    document: Mapped[Document] = relationship(back_populates="chunks")


class WatchState(Base):
    """Smart-polling state per source (module `watch`)."""

    __tablename__ = "watch_states"

    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    interval_s: Mapped[int] = mapped_column(Integer, default=300)
    min_interval_s: Mapped[int] = mapped_column(Integer, default=60)
    max_interval_s: Mapped[int] = mapped_column(Integer, default=900)
    next_run_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    last_change_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    errors_in_row: Mapped[int] = mapped_column(Integer, default=0)
    etag: Mapped[str | None] = mapped_column(String(200), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="ok")
    data_mode: Mapped[str] = mapped_column(String(16), default="real", index=True)


class Change(Base):
    __tablename__ = "changes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    ts: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    kind: Mapped[str] = mapped_column(String(24))  # quote_change | layout_change | status_change
    summary: Mapped[str] = mapped_column(Text, default="")
    before: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    after: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    evidence_id: Mapped[str | None] = mapped_column(ForeignKey("evidence.id", ondelete="SET NULL"), nullable=True)
    data_mode: Mapped[str] = mapped_column(String(16), default="real", index=True)


class AlertRule(Base):
    __tablename__ = "alert_rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(24))  # cycle_roi | quote_move | source_down | opportunity_new
    threshold: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    params: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
    channel: Mapped[str] = mapped_column(String(16), default="ui")  # ui | telegram | webhook | email
    target: Mapped[str | None] = mapped_column(Text, nullable=True)
    cooldown_s: Mapped[int] = mapped_column(Integer, default=600)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_fired_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    data_mode: Mapped[str] = mapped_column(String(16), default="real", index=True)


class AlertEvent(Base):
    __tablename__ = "alert_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    rule_id: Mapped[str] = mapped_column(ForeignKey("alert_rules.id", ondelete="CASCADE"), index=True)
    ts: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    message: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    channel: Mapped[str] = mapped_column(String(16))
    delivered: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_mode: Mapped[str] = mapped_column(String(16), default="real", index=True)


class Memory(Base):
    """Agent memory (module `memory`)."""

    __tablename__ = "memories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    kind: Mapped[str] = mapped_column(String(16))  # preference | decision | fact | outcome
    text: Mapped[str] = mapped_column(Text)
    tags: Mapped[list[Any]] = mapped_column(JSONType, default=list)
    source: Mapped[str] = mapped_column(String(8), default="user")  # user | agent
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    data_mode: Mapped[str] = mapped_column(String(16), default="real", index=True)


class Task(Base):
    """Collector jobs (on-demand quote requests, browser sessions)."""

    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_id: Mapped[str | None] = mapped_column(ForeignKey("sources.id", ondelete="SET NULL"), nullable=True)
    kind: Mapped[str] = mapped_column(String(32), default="fetch_quote")
    params: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_mode: Mapped[str] = mapped_column(String(16), default="real", index=True)
