from __future__ import annotations

from datetime import UTC, datetime

import pytest

from fronteira_fx.rag.retriever import (
    RRF_K,
    Bm25Index,
    HybridRetriever,
    make_snippet,
    reciprocal_rank_fusion,
)
from fronteira_fx.rag.store import ChunkRecord, DocumentRecord, InMemoryStore
from fronteira_fx.rag.text import tokenize

MODEL = "fixed-2d"


class FixedEmbedder:
    """Embedder de teste: devolve sempre o mesmo vetor de consulta (controla o ranking denso)."""

    name = MODEL
    dimensions = 2

    def __init__(self, query_vector: list[float]) -> None:
        self._vector = query_vector

    def embed(self, texts):
        return [list(self._vector) for _ in texts]


def _put(store: InMemoryStore, doc_id: str, text: str, vector: list[float], *, title: str = "", tags=()) -> None:
    search_text = "\n".join(part for part in (title, " ".join(tags), text) if part)
    chunk = ChunkRecord(
        id=f"{doc_id}#0",
        document_id=doc_id,
        index=0,
        text=text,
        search_text=search_text,
        embedding=tuple(vector),
        embedding_model=MODEL,
    )
    document = DocumentRecord(
        id=doc_id,
        title=title or doc_id,
        source=f"src-{doc_id}",
        tags=tuple(tags),
        text=text,
        content_hash="h",
        embedding_model=MODEL,
        chunk_count=1,
        created_at=datetime(2026, 11, 2, tzinfo=UTC),
    )
    store.replace_document(document, [chunk])


# --- BM25 -------------------------------------------------------------------------------------------


def test_bm25_prefers_documents_with_more_matching_terms():
    index = Bm25Index({"a": ["taxa", "efetiva", "taxa"], "b": ["taxa", "relacao"], "c": ["clima"]})
    ranked = index.rank(["taxa", "efetiva"])
    assert [doc for doc, _ in ranked] == ["a", "b"]
    assert "c" not in dict(ranked)


def test_bm25_rare_terms_weigh_more_than_common_ones():
    index = Bm25Index({"a": ["comum", "raro"], "b": ["comum"], "c": ["comum"]})
    scores_rare = dict(index.rank(["raro"]))
    scores_common = dict(index.rank(["comum"]))
    assert set(scores_rare) == {"a"}
    assert scores_rare["a"] > scores_common["a"]


def test_bm25_scores_are_positive_and_sorted_with_id_tiebreak():
    index = Bm25Index({"z": ["x"], "a": ["x"]})
    ranked = index.rank(["x"])
    assert [doc for doc, _ in ranked] == ["a", "z"]
    assert all(score > 0 for _, score in ranked)


def test_bm25_empty_corpus_returns_nothing():
    assert Bm25Index({}).rank(["qualquer"]) == []


# --- RRF --------------------------------------------------------------------------------------------


def test_rrf_sums_reciprocal_positions():
    fused = reciprocal_rank_fusion([["a", "b", "c"], ["b", "d", "a"]])
    assert fused["b"] == pytest.approx(1 / (RRF_K + 2) + 1 / (RRF_K + 1))
    assert fused["a"] == pytest.approx(1 / (RRF_K + 1) + 1 / (RRF_K + 3))
    assert fused["c"] == pytest.approx(1 / (RRF_K + 3))
    order = sorted(fused, key=lambda item: -fused[item])
    assert order == ["b", "a", "d", "c"]


def test_rrf_item_in_both_lists_beats_item_in_one_list_at_same_position():
    fused = reciprocal_rank_fusion([["x", "y"], ["y", "x"]])
    assert fused["x"] == fused["y"]  # simétrico: mesma soma de posições


# --- Hybrid search on a toy corpus ---------------------------------------------------------------


def test_hybrid_fusion_order_on_toy_corpus():
    store = InMemoryStore()
    # d1: casa com o texto E com o vetor; d3: só parcialmente no texto, mesmo vetor; d2: só vetor
    _put(store, "d1", "taxa efetiva taxa efetiva", [1.0, 0.0], title="Glossário")
    _put(store, "d2", "horários de abertura", [0.2, 1.0], title="Horários")
    _put(store, "d3", "taxa cobrada no balcão", [1.0, 0.0], title="Balcão")
    retriever = HybridRetriever(store, FixedEmbedder([1.0, 0.0]))

    hits = retriever.search("taxa efetiva", k=3)

    assert [h.document_id for h in hits] == ["d1", "d3", "d2"]
    assert hits[0].score == 1.0  # primeiro nos dois critérios
    assert hits[0].score > hits[1].score > hits[2].score > 0


def test_hybrid_excludes_documents_without_any_signal():
    store = InMemoryStore()
    _put(store, "d1", "taxa efetiva", [1.0, 0.0])
    _put(store, "d2", "clima", [-1.0, 0.0])  # cosseno negativo e sem palavra da consulta
    hits = HybridRetriever(store, FixedEmbedder([1.0, 0.0])).search("taxa", k=5)
    assert [h.document_id for h in hits] == ["d1"]


def test_hybrid_keeps_dense_only_hits():
    store = InMemoryStore()
    _put(store, "d1", "texto sem relação lexical", [0.9, 0.1])
    hits = HybridRetriever(store, FixedEmbedder([1.0, 0.0])).search("xyzzy", k=5)
    assert [h.document_id for h in hits] == ["d1"]


def test_hybrid_returns_one_hit_per_document_with_best_chunk():
    store = InMemoryStore()
    doc = DocumentRecord(
        id="d1",
        title="Doc",
        source="s",
        tags=(),
        text="",
        content_hash="h",
        embedding_model=MODEL,
        chunk_count=2,
        created_at=datetime(2026, 11, 2, tzinfo=UTC),
    )
    chunks = [
        ChunkRecord("d1#0", "d1", 0, "nada aqui", "Doc\nnada aqui", (), (1.0, 0.0), MODEL),
        ChunkRecord("d1#1", "d1", 1, "taxa efetiva aqui", "Doc\ntaxa efetiva aqui", (), (1.0, 0.0), MODEL),
    ]
    store.replace_document(doc, chunks)
    hits = HybridRetriever(store, FixedEmbedder([1.0, 0.0])).search("taxa efetiva", k=5)
    assert len(hits) == 1
    assert hits[0].chunk_id == "d1#1"
    assert "taxa efetiva" in hits[0].snippet


def test_tag_filter_restricts_candidates():
    store = InMemoryStore()
    _put(store, "d1", "taxa efetiva", [1.0, 0.0], tags=("cde",))
    _put(store, "d2", "taxa efetiva", [1.0, 0.0], tags=("pjc", "CDE-extra"))
    retriever = HybridRetriever(store, FixedEmbedder([1.0, 0.0]))
    assert [h.document_id for h in retriever.search("taxa", tag="cde")] == ["d1"]
    assert [h.document_id for h in retriever.search("taxa", tag="PJC")] == ["d2"]
    assert retriever.search("taxa", tag="inexistente") == []


def test_empty_query_and_empty_store_return_nothing():
    retriever = HybridRetriever(InMemoryStore(), FixedEmbedder([1.0, 0.0]))
    assert retriever.search("   ") == []
    assert retriever.search("taxa") == []


def test_k_must_be_positive():
    with pytest.raises(ValueError):
        HybridRetriever(InMemoryStore(), FixedEmbedder([1.0, 0.0])).search("x", k=0)


def test_query_with_only_stopwords_still_searches():
    store = InMemoryStore()
    _put(store, "d1", "the of and", [1.0, 0.0])
    hits = HybridRetriever(store, FixedEmbedder([1.0, 0.0])).search("the of", k=3)
    assert [h.document_id for h in hits] == ["d1"]


def test_tokenize_folds_accents_and_plurals():
    assert tokenize("Horários da Chaco") == ["horario", "chaco"]


# --- Snippets ---------------------------------------------------------------------------------------


def test_short_text_is_returned_whole_and_flat():
    assert make_snippet("linha\n  com   espaços", ["x"]) == "linha com espaços"


def test_long_text_snippet_is_bounded_and_centred_on_the_term():
    text = "palavra " * 200 + "alvo taxa efetiva aqui " + "fim " * 200
    snippet = make_snippet(text, ["efetiva"])
    assert len(snippet) <= 300
    assert "efetiva" in snippet
    assert snippet.startswith("…") and snippet.endswith("…")


def test_snippet_without_match_starts_at_the_beginning():
    snippet = make_snippet("x " * 500, ["nada"])
    assert len(snippet) <= 300
    assert not snippet.startswith("…")
    assert snippet.endswith("…")


def test_snippet_strips_markdown_emphasis():
    snippet = make_snippet("**Atenção**: `valor` a confirmar " * 30, ["valor"])
    assert "**" not in snippet and "`" not in snippet


def test_blank_tag_means_no_filter():
    store = InMemoryStore()
    _put(store, "d1", "taxa efetiva", [1.0, 0.0], tags=("cde",))
    _put(store, "d2", "taxa efetiva", [1.0, 0.0], tags=("pjc",))
    hits = HybridRetriever(store, FixedEmbedder([1.0, 0.0])).search("taxa", tag="  ", k=5)
    assert sorted(h.document_id for h in hits) == ["d1", "d2"]
