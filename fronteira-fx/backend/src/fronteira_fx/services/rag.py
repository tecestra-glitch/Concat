"""RAG corpus: documents + chunks with lexical (tf-idf) search. Quotes/calculations never come from here.

Embeddings: the `embedding` columns exist (pgvector on Postgres) but no provider is wired yet; search is lexical.

Knowledge base: `seed_knowledge()` loads `backend/knowledge/*.md` (front matter `title`/`source`/`tags`) into the
corpus, one `Document` per file keyed by `meta.path` + `meta.sha256`, so it is idempotent (B19).
"""

from __future__ import annotations

import hashlib
import logging
import math
import re
import unicodedata
from collections import Counter
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Document, DocumentChunk
from ..schemas import RagDocumentCreate, RagDocumentOut, RagHit

log = logging.getLogger("fronteira_fx.rag")

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


def _stem(token: str) -> str:
    """Very light pt/es stemming: drop a plural 's' (horarios -> horario, tarifas -> tarifa)."""
    return token[:-1] if len(token) > 4 and token.endswith("s") else token


def tokenize(text: str) -> list[str]:
    return [_stem(t) for t in _WORD.findall(normalize(text)) if len(t) > 1 and t not in STOPWORDS]


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


def default_knowledge_dir() -> Path:
    """`backend/knowledge` in a source checkout. Containers that install the package point `KNOWLEDGE_DIR` elsewhere."""
    return Path(__file__).resolve().parents[3] / "knowledge"


def _parse_front_matter(raw: str) -> tuple[dict[str, str], str]:
    """Leading `---` block of `key: value` lines (no YAML); keys lowercased. Without one, everything is body."""
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


def _knowledge_document(path: Path, raw: str, digest: str) -> RagDocumentCreate:
    meta, body = _parse_front_matter(raw)
    text = body.strip()
    title = meta.get("title") or _first_heading(text) or path.stem
    tags = [t.strip() for t in meta.get("tags", "").split(",") if t.strip()]
    return RagDocumentCreate(
        title=title[:300],
        text=text or title,
        source=(meta.get("source") or f"knowledge/{path.name}")[:200],
        tags=tags,
        metadata={"path": path.name, "sha256": digest},
    )


def seed_knowledge(session: Session, directory: Path | str, *, data_mode: str) -> dict[str, int]:
    """Seed every `*.md` under `directory` into the corpus of `data_mode`. Idempotent: a file whose sha256 matches
    the stored document is skipped; a changed file replaces its document (and chunks). Returns counts.

    This runs at API startup, so a bad file (unreadable, not UTF-8, invalid document) is logged and skipped
    (`skipped`) instead of raising; a previously seeded version of that file is kept."""
    stats = {"added": 0, "updated": 0, "unchanged": 0, "skipped": 0}
    directory = Path(directory)
    if not directory.is_dir():
        log.warning("knowledge dir %s não existe; nada semeado", directory)
        return stats
    current: dict[str, Document] = {}
    for doc in session.scalars(select(Document).where(Document.data_mode == data_mode)):
        meta = doc.meta or {}
        if meta.get("sha256") and meta.get("path"):
            current[str(meta["path"])] = doc
    for path in sorted(directory.glob("*.md")):
        try:
            raw = path.read_text(encoding="utf-8")
            digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
            existing = current.get(path.name)
            if existing is not None and existing.meta.get("sha256") == digest:
                stats["unchanged"] += 1
                continue
            data = _knowledge_document(path, raw, digest)  # validated before anything is deleted
        except (OSError, ValueError) as exc:  # UnicodeDecodeError and pydantic's ValidationError are ValueErrors
            log.warning("knowledge: %s ignorado (%s: %s)", path.name, type(exc).__name__, exc)
            stats["skipped"] += 1
            continue
        if existing is not None:
            session.delete(existing)  # cascades to the chunks
            session.flush()
            stats["updated"] += 1
        else:
            stats["added"] += 1
        add_document(session, data, data_mode=data_mode)
    return stats


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
