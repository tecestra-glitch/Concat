"""Busca híbrida: similaridade vetorial + BM25 (palavras-chave), fundidas por reciprocal rank fusion (RRF).

Fluxo de `HybridRetriever.search`:
1. filtra os documentos pela tag (se houver) e carrega os chunks candidatos;
2. ranqueia por BM25 sobre o `search_text` (título, tags, títulos internos e texto) e por cosseno;
3. funde os dois rankings com RRF: score = soma de 1/(k + posição), k = 60;
4. devolve no máximo um resultado por documento (o melhor chunk), com snippet de até 300 caracteres.

O `score` devolvido vai de 0 a 1: 1.0 significa primeiro lugar nos dois critérios.
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from .embeddings import Embedder
from .store import VectorStore
from .text import normalize_tag, tokenize

RRF_K = 60
SNIPPET_CHARS = 300
_POOL_PER_HIT = 5  # candidatos por ranking = max(k * 5, 20)
_POOL_MIN = 20
_WORD_RE = re.compile(r"[^\W_]+")


@dataclass(frozen=True, slots=True)
class SearchHit:
    chunk_id: str
    document_id: str
    title: str
    snippet: str
    score: float
    source: str
    tags: tuple[str, ...]


class Bm25Index:
    """BM25 mínimo (Okapi, com IDF de Lucene, sempre não negativo). Uma instância por consulta de corpus."""

    def __init__(self, documents: Mapping[str, Sequence[str]], *, k1: float = 1.5, b: float = 0.75) -> None:
        self._k1 = k1
        self._b = b
        self._tf: dict[str, Counter[str]] = {}
        self._length: dict[str, int] = {}
        document_freq: Counter[str] = Counter()
        for doc_id in sorted(documents):
            tokens = documents[doc_id]
            counts = Counter(tokens)
            self._tf[doc_id] = counts
            self._length[doc_id] = len(tokens)
            document_freq.update(counts.keys())
        n = len(self._tf)
        total = sum(self._length.values())
        self._avgdl = total / n if n else 0.0
        self._idf = {term: math.log(1 + (n - df + 0.5) / (df + 0.5)) for term, df in document_freq.items()}

    def rank(self, query_tokens: Iterable[str]) -> list[tuple[str, float]]:
        """Documentos com score > 0, do melhor para o pior (desempate por id)."""
        terms = sorted(set(query_tokens))
        scores: dict[str, float] = {}
        for doc_id, counts in self._tf.items():
            norm = self._k1 * (1 - self._b + self._b * self._length[doc_id] / self._avgdl) if self._avgdl else self._k1
            score = 0.0
            for term in terms:
                freq = counts.get(term, 0)
                if freq:
                    score += self._idf[term] * freq * (self._k1 + 1) / (freq + norm)
            if score > 0:
                scores[doc_id] = score
        return sorted(scores.items(), key=lambda item: (-item[1], item[0]))


def reciprocal_rank_fusion(rankings: Sequence[Sequence[str]], *, k: int = RRF_K) -> dict[str, float]:
    """Soma 1/(k + posição) de cada item em cada ranking (posição começa em 1)."""
    fused: defaultdict[str, float] = defaultdict(float)
    for ranking in rankings:
        for position, item in enumerate(ranking, start=1):
            fused[item] += 1.0 / (k + position)
    return dict(fused)


def make_snippet(text: str, terms: Iterable[str], *, max_chars: int = SNIPPET_CHARS) -> str:
    """Trecho de até `max_chars` centrado no primeiro termo da consulta, cortado em fronteira de palavra."""
    flat = " ".join(text.replace("**", "").replace("`", "").split())  # snippet é texto puro, sem marcação
    if len(flat) <= max_chars:
        return flat
    wanted = set(terms)
    anchor = 0
    for match in _WORD_RE.finditer(flat):
        if wanted.intersection(tokenize(match.group(0), drop_stopwords=False)):
            anchor = match.start()
            break
    start = max(0, anchor - max_chars // 3)
    if start > 0:
        space = flat.find(" ", start)
        start = space + 1 if space != -1 else start
    lead = "…" if start > 0 else ""
    end = min(len(flat), start + max_chars - len(lead) - 1)  # 1 caractere reservado para as reticências finais
    if end < len(flat):
        space = flat.rfind(" ", start, end + 1)
        if space > start:
            end = space
    tail = "…" if end < len(flat) else ""
    return f"{lead}{flat[start:end].strip()}{tail}"


class HybridRetriever:
    def __init__(self, store: VectorStore, embedder: Embedder, *, rrf_k: int = RRF_K) -> None:
        if rrf_k < 1:
            raise ValueError("rrf_k deve ser >= 1")
        self._store = store
        self._embedder = embedder
        self._rrf_k = rrf_k

    def search(self, query: str, *, k: int = 5, tag: str | None = None) -> list[SearchHit]:
        if k < 1:
            raise ValueError("k deve ser >= 1")
        if not query.strip():
            return []
        terms = tokenize(query) or tokenize(query, drop_stopwords=False)
        if not terms:
            return []

        documents = {doc.id: doc for doc in self._store.list_documents()}
        allowed: set[str] | None = None
        if tag is not None:
            wanted = normalize_tag(tag)
            allowed = {doc.id for doc in documents.values() if any(normalize_tag(t) == wanted for t in doc.tags)}
            if not allowed:
                return []

        chunks = self._store.iter_chunks(document_ids=allowed)
        if not chunks:
            return []
        chunks_by_id = {chunk.id: chunk for chunk in chunks}
        pool = max(k * _POOL_PER_HIT, _POOL_MIN)

        keyword_rank = [
            chunk_id for chunk_id, _ in Bm25Index({c.id: tokenize(c.search_text) for c in chunks}).rank(terms)[:pool]
        ]
        query_vector = self._embedder.embed([query])[0]
        dense_rank = [
            chunk_id
            for chunk_id, similarity in self._store.nearest(
                query_vector, model=self._embedder.name, limit=pool, document_ids=allowed
            )
            if similarity > 0
        ]

        fused = reciprocal_rank_fusion([keyword_rank, dense_rank], k=self._rrf_k)
        ranked = sorted(fused.items(), key=lambda item: (-item[1], item[0]))
        best_possible = 2 / (self._rrf_k + 1)

        hits: list[SearchHit] = []
        seen: set[str] = set()
        for chunk_id, score in ranked:
            chunk = chunks_by_id.get(chunk_id)
            if chunk is None or chunk.document_id in seen or chunk.document_id not in documents:
                continue
            seen.add(chunk.document_id)
            doc = documents[chunk.document_id]
            hits.append(
                SearchHit(
                    chunk_id=chunk.id,
                    document_id=doc.id,
                    title=doc.title,
                    snippet=make_snippet(chunk.text, terms),
                    score=round(min(1.0, score / best_possible), 4),
                    source=doc.source,
                    tags=doc.tags,
                )
            )
            if len(hits) == k:
                break
        return hits
