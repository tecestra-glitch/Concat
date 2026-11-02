"""RAG corpus: documents + chunks with lexical (tf-idf) search. Quotes/calculations never come from here.

Embeddings: the `embedding` columns exist (pgvector on Postgres) but no provider is wired yet; search is lexical.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Document, DocumentChunk
from ..schemas import RagDocumentCreate, RagDocumentOut, RagHit

STOPWORDS = {
    "a",
    "o",
    "e",
    "de",
    "da",
    "do",
    "das",
    "dos",
    "em",
    "um",
    "uma",
    "para",
    "com",
    "por",
    "que",
    "no",
    "na",
    "os",
    "as",
    "the",
    "of",
    "and",
    "to",
    "in",
    "is",
    "for",
    "on",
    "at",
    "el",
    "la",
    "los",
    "las",
    "y",
    "en",
    "con",
    "del",
    "se",
    "ao",
    "à",
    "é",
    "ou",
    "como",
    "mais",
    "sem",
    "sobre",
}
_WORD = re.compile(r"\w+", re.UNICODE)


def normalize(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(c))


def tokenize(text: str) -> list[str]:
    return [t for t in _WORD.findall(normalize(text)) if len(t) > 1 and t not in STOPWORDS]


def chunk_text(text: str, *, size: int = 800, overlap: int = 120) -> list[str]:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    current = ""
    for p in paragraphs:
        if len(current) + len(p) + 2 <= size:
            current = f"{current}\n\n{p}".strip()
            continue
        if current:
            chunks.append(current)
        while len(p) > size:
            chunks.append(p[:size])
            p = p[size - overlap :]
        current = p
    if current:
        chunks.append(current)
    return chunks or [text.strip()]


def add_document(session: Session, data: RagDocumentCreate, *, data_mode: str) -> Document:
    doc = Document(
        title=data.title,
        text=data.text,
        source=data.source,
        tags=list(data.tags),
        meta=dict(data.metadata or {}),
        data_mode=data_mode,
    )
    session.add(doc)
    session.flush()
    for i, chunk in enumerate(chunk_text(data.text)):
        session.add(DocumentChunk(document_id=doc.id, ord=i, text=chunk, tokens=tokenize(chunk), data_mode=data_mode))
    session.flush()
    return doc


def chunk_count(session: Session, document_id: str) -> int:
    return int(
        session.scalar(select(func.count(DocumentChunk.id)).where(DocumentChunk.document_id == document_id)) or 0
    )


def list_documents(session: Session, *, data_mode: str) -> list[RagDocumentOut]:
    docs = session.scalars(select(Document).where(Document.data_mode == data_mode).order_by(Document.created_at.desc()))
    return [
        RagDocumentOut(
            id=d.id,
            title=d.title,
            source=d.source,
            tags=list(d.tags or []),
            chunks=chunk_count(session, d.id),
            created_at=d.created_at,
        )
        for d in docs
    ]


def _snippet(text: str, terms: list[str], width: int = 220) -> str:
    norm = normalize(text)
    pos = min((norm.find(t) for t in terms if norm.find(t) >= 0), default=0)
    start = max(0, pos - width // 3)
    snippet = text[start : start + width].strip()
    return ("…" if start > 0 else "") + snippet + ("…" if start + width < len(text) else "")


def search(session: Session, q: str, *, k: int = 5, tag: str | None = None, data_mode: str) -> list[RagHit]:
    terms = tokenize(q)
    if not terms:
        return []
    stmt = (
        select(DocumentChunk, Document)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(DocumentChunk.data_mode == data_mode)
    )
    rows = [(c, d) for c, d in session.execute(stmt) if not tag or tag in (d.tags or [])]
    n = len(rows)
    if n == 0:
        return []
    df: Counter[str] = Counter()
    for c, _ in rows:
        df.update(set(c.tokens or []))
    hits: list[tuple[float, DocumentChunk, Document]] = []
    for c, d in rows:
        tf = Counter(c.tokens or [])
        title_tokens = set(tokenize(d.title or ""))
        score = 0.0
        for t in terms:
            if tf[t]:
                idf = math.log((n + 1) / (df[t] + 1)) + 1.0
                score += (1 + math.log(tf[t])) * idf
            if t in title_tokens:
                score += 0.5
        if score > 0:
            hits.append((score, c, d))
    hits.sort(key=lambda h: (-h[0], h[2].created_at, h[1].ord))
    return [
        RagHit(
            id=c.id,
            document_id=d.id,
            title=d.title,
            snippet=_snippet(c.text, terms),
            score=round(s, 4),
            source=d.source,
            tags=list(d.tags or []),
        )
        for s, c, d in hits[:k]
    ]
