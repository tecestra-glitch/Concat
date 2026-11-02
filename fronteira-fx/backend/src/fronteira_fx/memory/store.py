"""Armazenamento da memória do agente: contrato `MemoryStore`, implementação em memória e SQLAlchemy.

Expiração: uma memória com `expires_at <= now` deixa de existir para leitura (`get`, `recall`) e para
`delete`; `purge_expired()` a remove fisicamente.

Ranking de `recall(q=...)`: tokens sem acento e sem caixa; cada token da busca que aparece no texto vale 1
e cada token que bate com uma tag vale 2. Só entram itens com pontuação > 0. Empates (e buscas sem `q`)
são ordenados pelo mais recente.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any, Protocol, cast

from sqlalchemy import JSON, DateTime, Engine, Index, String, Text, TypeDecorator, delete, or_, select
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from .models import Memory, MemoryKind, MemorySource

TEXT_WEIGHT = 1
TAG_WEIGHT = 2

# Palavras de ligação em pt-BR e en: não contam como critério quando há outros termos na busca.
STOPWORDS = frozenset("a o os as de do da dos das e em um uma para por com no na nos nas ao the of and to in".split())

_TOKEN_RE = re.compile(r"\w+")


def fold(value: str) -> str:
    """Caixa baixa e sem acentos: 'Cartão' -> 'cartao'."""
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def tokens(value: str) -> set[str]:
    return set(_TOKEN_RE.findall(fold(value)))


def query_tokens(q: str) -> set[str]:
    words = tokens(q)
    return (words - STOPWORDS) or words


def _score(memory: Memory, query: set[str]) -> int:
    text_tokens = tokens(memory.text)
    tag_tokens: set[str] = set()
    for tag in memory.tags:
        tag_tokens |= tokens(tag)
    total = 0
    for term in query:
        if term in text_tokens:
            total += TEXT_WEIGHT
        if term in tag_tokens:
            total += TAG_WEIGHT
    return total


def select_memories(
    memories: Iterable[Memory], *, q: str | None = None, tag: str | None = None, limit: int = 20
) -> list[Memory]:
    """Filtra por tag, ordena por recência e, se houver `q`, por pontuação (estável: recência desempata)."""
    items = list(memories)
    if tag:
        wanted = fold(tag.strip())
        items = [m for m in items if any(fold(t) == wanted for t in m.tags)]
    items.sort(key=lambda m: m.created_at, reverse=True)
    terms = query_tokens(q) if q else set()
    if terms:
        scored = [(_score(m, terms), m) for m in items]
        scored = [pair for pair in scored if pair[0] > 0]
        scored.sort(key=lambda pair: pair[0], reverse=True)
        items = [m for _, m in scored]
    return items[:limit]


def _aware(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _is_active(memory: Memory, at: datetime) -> bool:
    return memory.expires_at is None or memory.expires_at > at


class MemoryStore(Protocol):
    """Contrato de armazenamento. `now` é injetável para testes de TTL; omitido, usa o relógio real."""

    def add(self, memory: Memory) -> None: ...

    def get(self, memory_id: str, *, now: datetime | None = None) -> Memory | None: ...

    def delete(self, memory_id: str, *, now: datetime | None = None) -> bool: ...

    def recall(
        self,
        *,
        q: str | None = None,
        kind: MemoryKind | None = None,
        tag: str | None = None,
        limit: int = 20,
        now: datetime | None = None,
    ) -> list[Memory]: ...

    def purge_expired(self, *, now: datetime | None = None) -> int: ...


class InMemoryStore:
    """Armazenamento volátil (testes, modo demo, ou antes de o core plugar o banco)."""

    def __init__(self) -> None:
        self._items: dict[str, Memory] = {}

    def add(self, memory: Memory) -> None:
        self._items[memory.id] = memory

    def get(self, memory_id: str, *, now: datetime | None = None) -> Memory | None:
        memory = self._items.get(memory_id)
        if memory is None or not _is_active(memory, _aware(now)):
            return None
        return memory

    def delete(self, memory_id: str, *, now: datetime | None = None) -> bool:
        if self.get(memory_id, now=now) is None:
            return False
        del self._items[memory_id]
        return True

    def recall(
        self,
        *,
        q: str | None = None,
        kind: MemoryKind | None = None,
        tag: str | None = None,
        limit: int = 20,
        now: datetime | None = None,
    ) -> list[Memory]:
        at = _aware(now)
        # reversed: entre inserções com o mesmo instante, a mais nova aparece primeiro
        active = [
            m for m in reversed(list(self._items.values())) if _is_active(m, at) and (kind is None or m.kind == kind)
        ]
        return select_memories(active, q=q, tag=tag, limit=limit)

    def purge_expired(self, *, now: datetime | None = None) -> int:
        at = _aware(now)
        expired = [key for key, m in self._items.items() if not _is_active(m, at)]
        for key in expired:
            del self._items[key]
        return len(expired)


class MemoryBase(DeclarativeBase):
    """Base própria do módulo: a tabela `agent_memories` não depende de `models.Base`.

    Alembic: `target_metadata = [Base.metadata, MemoryBase.metadata]` (autogenerate aceita sequência).
    """


class _UTCDateTime(TypeDecorator[datetime]):
    """Grava UTC (SQLite não guarda fuso) e devolve datetime aware em UTC."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Dialect) -> Any:
        if value is None:
            return None
        aware = _aware(value)
        return aware.replace(tzinfo=None) if dialect.name == "sqlite" else aware

    def process_result_value(self, value: Any, dialect: Dialect) -> Any:
        if value is None:
            return None
        return _aware(value)


class MemoryRow(MemoryBase):
    __tablename__ = "agent_memories"
    __table_args__ = (Index("ix_agent_memories_kind_created", "kind", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    kind: Mapped[str] = mapped_column(String(16))
    text: Mapped[str] = mapped_column(Text)
    tags: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    source: Mapped[str] = mapped_column(String(8))
    created_at: Mapped[datetime] = mapped_column(_UTCDateTime, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(_UTCDateTime, nullable=True, index=True)


def create_memory_tables(engine: Engine) -> None:
    """Cria `agent_memories` (uso em dev/testes; em produção prefira migração Alembic)."""
    MemoryBase.metadata.create_all(engine)


def _to_row(memory: Memory) -> MemoryRow:
    return MemoryRow(
        id=memory.id,
        kind=memory.kind,
        text=memory.text,
        tags=list(memory.tags),
        source=memory.source,
        created_at=memory.created_at,
        expires_at=memory.expires_at,
    )


def _to_memory(row: MemoryRow) -> Memory:
    return Memory(
        id=row.id,
        kind=cast(MemoryKind, row.kind),
        text=row.text,
        tags=list(row.tags),
        created_at=row.created_at,
        expires_at=row.expires_at,
        source=cast(MemorySource, row.source),
    )


def _active_clause(at: datetime) -> Any:
    return or_(MemoryRow.expires_at.is_(None), MemoryRow.expires_at > at)


class SqlStore:
    """Armazenamento SQLAlchemy (SQLite ou PostgreSQL). Cada operação abre e fecha a sua transação.

    A busca filtra `kind` e a expiração no banco e pontua o texto em Python: para o volume de uma
    memória pessoal isso basta; se crescer, troque por FTS/índice sem mudar a API.
    """

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._factory = session_factory

    def add(self, memory: Memory) -> None:
        with self._factory() as session, session.begin():
            session.add(_to_row(memory))

    def get(self, memory_id: str, *, now: datetime | None = None) -> Memory | None:
        at = _aware(now)
        with self._factory() as session:
            row = session.scalar(select(MemoryRow).where(MemoryRow.id == memory_id, _active_clause(at)))
            return _to_memory(row) if row is not None else None

    def delete(self, memory_id: str, *, now: datetime | None = None) -> bool:
        at = _aware(now)
        with self._factory() as session, session.begin():
            deleted = session.scalars(
                delete(MemoryRow).where(MemoryRow.id == memory_id, _active_clause(at)).returning(MemoryRow.id)
            ).all()
            return len(deleted) > 0

    def recall(
        self,
        *,
        q: str | None = None,
        kind: MemoryKind | None = None,
        tag: str | None = None,
        limit: int = 20,
        now: datetime | None = None,
    ) -> list[Memory]:
        at = _aware(now)
        stmt = select(MemoryRow).where(_active_clause(at))
        if kind is not None:
            stmt = stmt.where(MemoryRow.kind == kind)
        stmt = stmt.order_by(MemoryRow.created_at.desc())
        if not q and not tag:
            # sem filtro em Python, o corte pode ir para o banco
            stmt = stmt.limit(limit)
        with self._factory() as session:
            memories = [_to_memory(row) for row in session.scalars(stmt)]
        return select_memories(memories, q=q, tag=tag, limit=limit)

    def purge_expired(self, *, now: datetime | None = None) -> int:
        at = _aware(now)
        with self._factory() as session, session.begin():
            deleted = session.scalars(
                delete(MemoryRow)
                .where(MemoryRow.expires_at.is_not(None), MemoryRow.expires_at <= at)
                .returning(MemoryRow.id)
            ).all()
            return len(deleted)
