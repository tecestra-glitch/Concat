"""Armazenamento do RAG: `InMemoryStore` (testes e desenvolvimento) e `SqlStore` (SQLAlchemy 2).

`SqlStore` usa o próprio `RagBase` (tabelas `rag_documents` e `rag_chunks`), separado do Base do núcleo.
Em PostgreSQL com o pacote `pgvector` importável, o embedding vai para `vector(384)` e a busca usa `<=>`.
Nos demais bancos o embedding fica em JSON e a similaridade é calculada em Python.

Para o Alembic: incluir `RagBase.metadata` no `target_metadata` (aceita uma sequência de MetaData).
"""

from __future__ import annotations

import threading
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable

from sqlalchemy import JSON, DateTime, Engine, Float, ForeignKey, Integer, String, Text, delete, select, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.types import TypeDecorator

from .embeddings import EMBEDDING_DIM, cosine

try:
    from pgvector.sqlalchemy import Vector as PgVector
except ImportError:  # pgvector é opcional: sem o pacote, o embedding fica em JSON mesmo no PostgreSQL
    PgVector = None


@dataclass(frozen=True, slots=True)
class DocumentRecord:
    id: str
    title: str
    source: str
    tags: tuple[str, ...]
    text: str
    content_hash: str
    embedding_model: str
    chunk_count: int
    created_at: datetime
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ChunkRecord:
    id: str
    document_id: str
    index: int
    text: str
    search_text: str
    heading_path: tuple[str, ...] = ()
    embedding: tuple[float, ...] | None = None
    embedding_model: str | None = None


@runtime_checkable
class VectorStore(Protocol):
    """Contrato mínimo. `document_ids=None` significa "todos"; uma coleção vazia significa "nenhum"."""

    def replace_document(self, document: DocumentRecord, chunks: Sequence[ChunkRecord]) -> None: ...

    def delete_document(self, document_id: str) -> bool: ...

    def get_document(self, document_id: str) -> DocumentRecord | None: ...

    def list_documents(self) -> list[DocumentRecord]: ...

    def iter_chunks(self, *, document_ids: Collection[str] | None = None) -> list[ChunkRecord]:
        """Chunks sem vetor (o recuperador de palavras-chave só precisa do texto)."""
        ...

    def nearest(
        self,
        vector: Sequence[float],
        *,
        model: str,
        limit: int,
        document_ids: Collection[str] | None = None,
    ) -> list[tuple[str, float]]:
        """(chunk_id, similaridade cosseno) em ordem decrescente, só para o `model` informado."""
        ...


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class InMemoryStore:
    """Armazenamento em memória, protegido por lock (as rotas síncronas rodam em threadpool)."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._documents: dict[str, DocumentRecord] = {}
        self._chunks: dict[str, ChunkRecord] = {}
        self._chunk_ids: dict[str, list[str]] = {}

    def replace_document(self, document: DocumentRecord, chunks: Sequence[ChunkRecord]) -> None:
        if any(chunk.document_id != document.id for chunk in chunks):
            raise ValueError("chunk pertence a outro documento")
        with self._lock:
            self._remove(document.id)
            self._documents[document.id] = document
            for chunk in chunks:
                self._chunks[chunk.id] = chunk
            self._chunk_ids[document.id] = [chunk.id for chunk in chunks]

    def delete_document(self, document_id: str) -> bool:
        with self._lock:
            existed = document_id in self._documents
            self._remove(document_id)
            return existed

    def _remove(self, document_id: str) -> None:
        self._documents.pop(document_id, None)
        for chunk_id in self._chunk_ids.pop(document_id, []):
            self._chunks.pop(chunk_id, None)

    def get_document(self, document_id: str) -> DocumentRecord | None:
        with self._lock:
            return self._documents.get(document_id)

    def list_documents(self) -> list[DocumentRecord]:
        with self._lock:
            return sorted(self._documents.values(), key=lambda d: (d.created_at, d.id))

    def iter_chunks(self, *, document_ids: Collection[str] | None = None) -> list[ChunkRecord]:
        allowed = None if document_ids is None else set(document_ids)
        with self._lock:
            chunks = [c for c in self._chunks.values() if allowed is None or c.document_id in allowed]
        chunks.sort(key=lambda c: (c.document_id, c.index))
        return [replace(c, embedding=None) for c in chunks]

    def nearest(
        self,
        vector: Sequence[float],
        *,
        model: str,
        limit: int,
        document_ids: Collection[str] | None = None,
    ) -> list[tuple[str, float]]:
        if limit < 1:
            raise ValueError("limit deve ser >= 1")
        allowed = None if document_ids is None else set(document_ids)
        scored: list[tuple[str, float]] = []
        with self._lock:
            for chunk in self._chunks.values():
                if chunk.embedding is None or chunk.embedding_model != model:
                    continue
                if allowed is not None and chunk.document_id not in allowed:
                    continue
                if len(chunk.embedding) != len(vector):
                    continue
                scored.append((chunk.id, cosine(vector, chunk.embedding)))
        scored.sort(key=lambda item: (-item[1], item[0]))
        return scored[:limit]


class RagBase(DeclarativeBase):
    """Metadados do RAG. Não compartilha o Base do núcleo."""


class _EmbeddingType(TypeDecorator[list[float]]):
    """`vector(N)` do pgvector em PostgreSQL (se o pacote existir); JSON em qualquer outro banco."""

    impl = JSON
    cache_ok = True

    def __init__(self, dimensions: int = EMBEDDING_DIM) -> None:
        super().__init__()
        self.dimensions = dimensions

    def load_dialect_impl(self, dialect: Any) -> Any:
        if dialect.name == "postgresql" and PgVector is not None:
            return dialect.type_descriptor(PgVector(self.dimensions))
        return dialect.type_descriptor(JSON())

    def process_bind_param(self, value: Any, dialect: Any) -> list[float] | None:
        if value is None:
            return None
        return [float(x) for x in value]

    def process_result_value(self, value: Any, dialect: Any) -> list[float] | None:
        if value is None:
            return None
        return [float(x) for x in value]


class DocumentRow(RagBase):
    __tablename__ = "rag_documents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    source: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    doc_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, nullable=False, default=dict)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    embedding_model: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ChunkRow(RagBase):
    __tablename__ = "rag_chunks"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    document_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("rag_documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    idx: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    search_text: Mapped[str] = mapped_column(Text, nullable=False)
    heading_path: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    embedding: Mapped[list[float] | None] = mapped_column(_EmbeddingType(), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)


class SqlStore:
    """Armazenamento SQLAlchemy. Cria as tabelas com `create_schema()` ou via Alembic (ver docs/rag.md)."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._sessions = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
        self._pgvector = engine.dialect.name == "postgresql" and PgVector is not None

    @property
    def uses_pgvector(self) -> bool:
        return self._pgvector

    def create_schema(self) -> None:
        if self._pgvector:
            with self._engine.begin() as conn:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        RagBase.metadata.create_all(self._engine)

    def replace_document(self, document: DocumentRecord, chunks: Sequence[ChunkRecord]) -> None:
        if any(chunk.document_id != document.id for chunk in chunks):
            raise ValueError("chunk pertence a outro documento")
        with self._sessions.begin() as session:
            session.execute(delete(ChunkRow).where(ChunkRow.document_id == document.id))
            session.execute(delete(DocumentRow).where(DocumentRow.id == document.id))
            session.add(_document_row(document))
            session.add_all([_chunk_row(chunk) for chunk in chunks])

    def delete_document(self, document_id: str) -> bool:
        with self._sessions.begin() as session:
            session.execute(delete(ChunkRow).where(ChunkRow.document_id == document_id))
            result = session.execute(delete(DocumentRow).where(DocumentRow.id == document_id))
            return bool(result.rowcount)  # type: ignore[attr-defined]

    def get_document(self, document_id: str) -> DocumentRecord | None:
        with self._sessions() as session:
            row = session.get(DocumentRow, document_id)
            return _document_record(row) if row is not None else None

    def list_documents(self) -> list[DocumentRecord]:
        with self._sessions() as session:
            rows = session.scalars(select(DocumentRow).order_by(DocumentRow.created_at, DocumentRow.id)).all()
            return [_document_record(row) for row in rows]

    def iter_chunks(self, *, document_ids: Collection[str] | None = None) -> list[ChunkRecord]:
        stmt = select(
            ChunkRow.id,
            ChunkRow.document_id,
            ChunkRow.idx,
            ChunkRow.text,
            ChunkRow.search_text,
            ChunkRow.heading_path,
            ChunkRow.embedding_model,
        ).order_by(ChunkRow.document_id, ChunkRow.idx)
        if document_ids is not None:
            ids = list(document_ids)
            if not ids:
                return []
            stmt = stmt.where(ChunkRow.document_id.in_(ids))
        with self._sessions() as session:
            rows = session.execute(stmt).all()
        return [
            ChunkRecord(
                id=row.id,
                document_id=row.document_id,
                index=row.idx,
                text=row.text,
                search_text=row.search_text,
                heading_path=tuple(row.heading_path or ()),
                embedding=None,
                embedding_model=row.embedding_model,
            )
            for row in rows
        ]

    def nearest(
        self,
        vector: Sequence[float],
        *,
        model: str,
        limit: int,
        document_ids: Collection[str] | None = None,
    ) -> list[tuple[str, float]]:
        if limit < 1:
            raise ValueError("limit deve ser >= 1")
        ids = None if document_ids is None else list(document_ids)
        if ids is not None and not ids:
            return []
        if self._pgvector:
            stmt = nearest_statement_pgvector(vector, model=model, limit=limit, ids=ids)
            with self._sessions() as session:
                rows = session.execute(stmt).all()
            return [(row.id, float(row.similarity)) for row in rows]
        stmt = select(ChunkRow.id, ChunkRow.embedding).where(ChunkRow.embedding_model == model)
        if ids is not None:
            stmt = stmt.where(ChunkRow.document_id.in_(ids))
        with self._sessions() as session:
            rows = session.execute(stmt).all()
        scored = [
            (row.id, cosine(vector, row.embedding))
            for row in rows
            if row.embedding is not None and len(row.embedding) == len(vector)
        ]
        scored.sort(key=lambda item: (-item[1], item[0]))
        return scored[:limit]

def nearest_statement_pgvector(
    vector: Sequence[float], *, model: str, limit: int, ids: Collection[str] | None
) -> Any:
    """SELECT id, 1 - (embedding <=> :vector) ORDER BY distância. Usa o operador de cosseno do pgvector."""
    distance = ChunkRow.embedding.op("<=>", return_type=Float)(list(vector))
    stmt = (
        select(ChunkRow.id, (1 - distance).label("similarity"))
        .where(ChunkRow.embedding_model == model)
        .order_by(distance)
        .limit(limit)
    )
    if ids is not None:
        stmt = stmt.where(ChunkRow.document_id.in_(list(ids)))
    return stmt


def _document_row(document: DocumentRecord) -> DocumentRow:
    return DocumentRow(
        id=document.id,
        title=document.title,
        source=document.source,
        tags=list(document.tags),
        text=document.text,
        doc_metadata=dict(document.metadata),
        content_hash=document.content_hash,
        embedding_model=document.embedding_model,
        chunk_count=document.chunk_count,
        created_at=document.created_at,
    )


def _document_record(row: DocumentRow) -> DocumentRecord:
    return DocumentRecord(
        id=row.id,
        title=row.title,
        source=row.source,
        tags=tuple(row.tags or ()),
        text=row.text,
        content_hash=row.content_hash,
        embedding_model=row.embedding_model,
        chunk_count=row.chunk_count,
        created_at=_as_utc(row.created_at),
        metadata=dict(row.doc_metadata or {}),
    )


def _chunk_row(chunk: ChunkRecord) -> ChunkRow:
    return ChunkRow(
        id=chunk.id,
        document_id=chunk.document_id,
        idx=chunk.index,
        text=chunk.text,
        search_text=chunk.search_text,
        heading_path=list(chunk.heading_path),
        embedding=list(chunk.embedding) if chunk.embedding is not None else None,
        embedding_model=chunk.embedding_model,
    )
