"""Serviço do RAG: adiciona documentos, carrega a base de conhecimento em `knowledge/` e pesquisa.

Regras de uso:
- O RAG devolve documentação, tarifas (texto), horários e trechos de evidência. Cotações e cálculos
  nunca passam por aqui: vêm do banco e do motor.
- `seed()` é idempotente: cada arquivo tem id estável (`seed-<nome>`) e um hash do conteúdo somado ao
  nome do embedder. Arquivo sem mudança é pulado; trocar o embedder reindexa só o que for necessário.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .chunking import DEFAULT_MAX_TOKENS, DEFAULT_OVERLAP_TOKENS, chunk_text, validate_window
from .embeddings import Embedder
from .retriever import HybridRetriever, SearchHit
from .store import ChunkRecord, DocumentRecord, VectorStore
from .text import normalize_tag

MAX_TITLE_CHARS = 300
MAX_SOURCE_CHARS = 500
MAX_TAG_CHARS = 40
MAX_TAGS = 20
MAX_DOC_ID_CHARS = 64


@dataclass(frozen=True, slots=True)
class SeedResult:
    document_id: str
    title: str
    chunks: int
    changed: bool  # False quando o arquivo não mudou e foi pulado


def parse_front_matter(raw: str) -> tuple[dict[str, str], str]:
    """Bloco `---` no topo com pares `chave: valor` (sem YAML). Sem bloco válido, o texto inteiro é corpo."""
    lines = raw.replace("\r\n", "\n").split("\n")
    if not lines or lines[0].strip() != "---":
        return {}, raw
    for end in range(1, len(lines)):
        if lines[end].strip() == "---":
            meta: dict[str, str] = {}
            for line in lines[1:end]:
                key, sep, value = line.partition(":")
                if sep and key.strip():
                    meta[key.strip().lower()] = value.strip()
            return meta, "\n".join(lines[end + 1 :])
    return {}, raw


def _first_heading(body: str) -> str | None:
    for line in body.splitlines():
        if line.startswith("# "):
            return line[2:].strip() or None
    return None


def _required(value: str, field_name: str, max_chars: int) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        raise ValueError(f"{field_name} é obrigatório")
    if len(cleaned) > max_chars:
        raise ValueError(f"{field_name} excede {max_chars} caracteres")
    return cleaned


def _clean_tags(tags: Iterable[str]) -> tuple[str, ...]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in tags:
        tag = " ".join(str(raw).split())
        if not tag:
            continue
        if len(tag) > MAX_TAG_CHARS:
            raise ValueError(f"tag com mais de {MAX_TAG_CHARS} caracteres: {tag[:20]}...")
        key = normalize_tag(tag)
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(tag)
    if len(cleaned) > MAX_TAGS:
        raise ValueError(f"no máximo {MAX_TAGS} tags por documento")
    return tuple(cleaned)


def _split_tags(value: str) -> tuple[str, ...]:
    return _clean_tags(part for part in value.split(",")) if value else ()


class RagService:
    def __init__(
        self,
        store: VectorStore,
        embedder: Embedder,
        *,
        chunk_tokens: int = DEFAULT_MAX_TOKENS,
        overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
    ) -> None:
        validate_window(chunk_tokens, overlap_tokens)
        self._store = store
        self._embedder = embedder
        self._chunk_tokens = chunk_tokens
        self._overlap_tokens = overlap_tokens
        self._retriever = HybridRetriever(store, embedder)

    @property
    def embedder_name(self) -> str:
        return self._embedder.name

    def add_document(
        self,
        title: str,
        text: str,
        source: str,
        tags: Iterable[str] = (),
        metadata: Mapping[str, Any] | None = None,
        *,
        document_id: str | None = None,
    ) -> tuple[str, int]:
        """Indexa (ou substitui, se `document_id` já existir) um documento. Devolve (id, n_chunks)."""
        clean_title = _required(title, "title", MAX_TITLE_CHARS)
        body = (text or "").strip()
        if not body:
            raise ValueError("text é obrigatório")
        clean_source = (source or "").strip()[:MAX_SOURCE_CHARS]
        clean_tags = _clean_tags(tags)
        doc_id = document_id or uuid.uuid4().hex
        if not doc_id or len(doc_id) > MAX_DOC_ID_CHARS:
            raise ValueError(f"document_id deve ter entre 1 e {MAX_DOC_ID_CHARS} caracteres")
        return self._index(
            doc_id,
            clean_title,
            body,
            clean_source,
            clean_tags,
            dict(metadata or {}),
            created_at=datetime.now(UTC),
            digest=self._digest(clean_title, clean_source, clean_tags, body),
        )

    def search(self, query: str, *, k: int = 5, tag: str | None = None) -> list[SearchHit]:
        return self._retriever.search(query, k=k, tag=tag)

    def list_documents(self) -> list[DocumentRecord]:
        return self._store.list_documents()

    def get_document(self, document_id: str) -> DocumentRecord | None:
        return self._store.get_document(document_id)

    def delete_document(self, document_id: str) -> bool:
        return self._store.delete_document(document_id)

    def seed(self, directory: str | Path) -> list[SeedResult]:
        """Carrega `*.md` do diretório (ordem alfabética). Front matter opcional: title, source, tags."""
        root = Path(directory)
        if not root.is_dir():
            raise FileNotFoundError(f"diretório de conhecimento não existe: {root}")
        results: list[SeedResult] = []
        for path in sorted(root.glob("*.md")):
            meta, body = parse_front_matter(path.read_text(encoding="utf-8"))
            title = meta.get("title") or _first_heading(body) or path.stem
            source = meta.get("source") or f"knowledge/{path.name}"
            tags = _split_tags(meta.get("tags", ""))
            results.append(self._seed_one(f"seed-{path.stem}", title, source, tags, body.strip(), path.name))
        return results

    def reindex(self) -> int:
        """Recalcula os vetores de todos os documentos (use após trocar o provedor de embeddings)."""
        count = 0
        for doc in self._store.list_documents():
            self._index(
                doc.id,
                doc.title,
                doc.text,
                doc.source,
                doc.tags,
                dict(doc.metadata),
                created_at=doc.created_at,
                digest=self._digest(doc.title, doc.source, doc.tags, doc.text),
            )
            count += 1
        return count

    def _seed_one(
        self,
        doc_id: str,
        title: str,
        source: str,
        tags: tuple[str, ...],
        body: str,
        file_name: str,
    ) -> SeedResult:
        digest = self._digest(title, source, tags, body)
        existing = self._store.get_document(doc_id)
        if existing is not None and existing.content_hash == digest:
            return SeedResult(doc_id, title, existing.chunk_count, changed=False)
        created = existing.created_at if existing is not None else datetime.now(UTC)
        _, count = self._index(
            doc_id,
            title,
            body,
            source,
            tags,
            {"file": file_name},
            created_at=created,
            digest=digest,
        )
        return SeedResult(doc_id, title, count, changed=True)

    def _digest(self, title: str, source: str, tags: Iterable[str], text: str) -> str:
        payload = {
            "title": title,
            "source": source,
            "tags": list(tags),
            "text": text,
            "embedder": self._embedder.name,
            "window": [self._chunk_tokens, self._overlap_tokens],
        }
        encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def _index(
        self,
        doc_id: str,
        title: str,
        text: str,
        source: str,
        tags: tuple[str, ...],
        metadata: dict[str, Any],
        *,
        created_at: datetime,
        digest: str,
    ) -> tuple[str, int]:
        pieces = chunk_text(text, max_tokens=self._chunk_tokens, overlap_tokens=self._overlap_tokens)
        if not pieces:
            raise ValueError("documento sem conteúdo indexável")
        search_texts = [_search_text(title, tags, piece.heading_path, piece.text) for piece in pieces]
        vectors = self._embedder.embed(search_texts)
        if len(vectors) != len(pieces):
            raise RuntimeError("o embedder devolveu quantidade diferente de vetores")
        model = self._embedder.name
        chunks = [
            ChunkRecord(
                id=f"{doc_id}#{piece.index}",
                document_id=doc_id,
                index=piece.index,
                text=piece.text,
                search_text=search,
                heading_path=piece.heading_path,
                embedding=tuple(vector),
                embedding_model=model,
            )
            for piece, search, vector in zip(pieces, search_texts, vectors, strict=True)
        ]
        document = DocumentRecord(
            id=doc_id,
            title=title,
            source=source,
            tags=tags,
            text=text,
            content_hash=digest,
            embedding_model=model,
            chunk_count=len(chunks),
            created_at=created_at,
            metadata=metadata,
        )
        self._store.replace_document(document, chunks)
        return doc_id, len(chunks)


def _search_text(title: str, tags: Iterable[str], heading_path: tuple[str, ...], text: str) -> str:
    parts = [title, " > ".join(heading_path), " ".join(tags), text]
    return "\n".join(part for part in parts if part)
