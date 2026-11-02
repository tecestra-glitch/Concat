from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects import postgresql
from sqlalchemy.pool import StaticPool
from sqlalchemy.schema import CreateTable

from fronteira_fx.rag import store as store_module
from fronteira_fx.rag.store import (
    ChunkRecord,
    ChunkRow,
    DocumentRecord,
    InMemoryStore,
    RagBase,
    SqlStore,
    VectorStore,
    nearest_statement_pgvector,
)

CREATED = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)


@pytest.fixture(params=["memory", "sqlite"])
def store(request) -> Iterator[VectorStore]:
    if request.param == "memory":
        yield InMemoryStore()
        return
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    sql_store = SqlStore(engine)
    sql_store.create_schema()
    yield sql_store
    engine.dispose()


def _doc(doc_id: str, *, tags=("cde",), title="Doc", chunk_count=2) -> DocumentRecord:
    return DocumentRecord(
        id=doc_id,
        title=title,
        source=f"https://{doc_id}.example",
        tags=tuple(tags),
        text="texto completo do documento",
        content_hash="abc",
        embedding_model="m1",
        chunk_count=chunk_count,
        created_at=CREATED,
        metadata={"file": "x.md", "n": 2},
    )


def _chunk(doc_id: str, index: int, vector, *, model="m1", heading=("Tarifas", "Chaco")) -> ChunkRecord:
    return ChunkRecord(
        id=f"{doc_id}#{index}",
        document_id=doc_id,
        index=index,
        text=f"trecho {index} de {doc_id}",
        search_text=f"Doc\ntrecho {index}",
        heading_path=heading,
        embedding=tuple(vector) if vector is not None else None,
        embedding_model=model,
    )


def test_replace_then_get_and_list_round_trip(store: VectorStore):
    store.replace_document(_doc("d1"), [_chunk("d1", 0, [1.0, 0.0]), _chunk("d1", 1, [0.0, 1.0])])
    got = store.get_document("d1")
    assert got is not None
    assert got.title == "Doc"
    assert got.tags == ("cde",)
    assert dict(got.metadata) == {"file": "x.md", "n": 2}
    assert got.created_at == CREATED
    assert [d.id for d in store.list_documents()] == ["d1"]
    assert store.get_document("nope") is None


def test_replace_overwrites_previous_chunks(store: VectorStore):
    store.replace_document(_doc("d1"), [_chunk("d1", 0, [1.0, 0.0]), _chunk("d1", 1, [0.0, 1.0])])
    store.replace_document(_doc("d1", title="Novo", chunk_count=1), [_chunk("d1", 0, [1.0, 0.0])])
    assert [d.title for d in store.list_documents()] == ["Novo"]
    assert [c.id for c in store.iter_chunks()] == ["d1#0"]


def test_iter_chunks_is_ordered_and_has_no_vectors(store: VectorStore):
    store.replace_document(_doc("d2"), [_chunk("d2", 0, [1.0, 0.0])])
    store.replace_document(_doc("d1"), [_chunk("d1", 1, [1.0, 0.0]), _chunk("d1", 0, [1.0, 0.0])])
    chunks = store.iter_chunks()
    assert [(c.document_id, c.index) for c in chunks] == [("d1", 0), ("d1", 1), ("d2", 0)]
    assert all(c.embedding is None for c in chunks)
    assert chunks[0].heading_path == ("Tarifas", "Chaco")
    assert chunks[0].search_text.startswith("Doc\n")


def test_iter_chunks_filters_by_document_ids(store: VectorStore):
    store.replace_document(_doc("d1"), [_chunk("d1", 0, [1.0, 0.0])])
    store.replace_document(_doc("d2"), [_chunk("d2", 0, [1.0, 0.0])])
    assert [c.document_id for c in store.iter_chunks(document_ids={"d2"})] == ["d2"]
    assert store.iter_chunks(document_ids=set()) == []


def test_delete_removes_document_and_chunks(store: VectorStore):
    store.replace_document(_doc("d1"), [_chunk("d1", 0, [1.0, 0.0])])
    assert store.delete_document("d1") is True
    assert store.delete_document("d1") is False
    assert store.get_document("d1") is None
    assert store.iter_chunks() == []


def test_nearest_orders_by_cosine_and_respects_limit(store: VectorStore):
    store.replace_document(
        _doc("d1"),
        [_chunk("d1", 0, [1.0, 0.0]), _chunk("d1", 1, [0.6, 0.8]), _chunk("d1", 2, [0.0, 1.0])],
    )
    result = store.nearest([1.0, 0.0], model="m1", limit=2)
    assert [chunk_id for chunk_id, _ in result] == ["d1#0", "d1#1"]
    assert result[0][1] == pytest.approx(1.0)
    assert result[1][1] == pytest.approx(0.6)


def test_nearest_ignores_other_models_and_missing_vectors(store: VectorStore):
    store.replace_document(
        _doc("d1"),
        [
            _chunk("d1", 0, [1.0, 0.0], model="m1"),
            _chunk("d1", 1, [1.0, 0.0], model="m2"),
            _chunk("d1", 2, None, model="m1"),
        ],
    )
    assert [cid for cid, _ in store.nearest([1.0, 0.0], model="m1", limit=5)] == ["d1#0"]
    assert [cid for cid, _ in store.nearest([1.0, 0.0], model="m2", limit=5)] == ["d1#1"]


def test_nearest_respects_document_filter(store: VectorStore):
    store.replace_document(_doc("d1"), [_chunk("d1", 0, [1.0, 0.0])])
    store.replace_document(_doc("d2"), [_chunk("d2", 0, [1.0, 0.0])])
    assert [cid for cid, _ in store.nearest([1.0, 0.0], model="m1", limit=5, document_ids={"d2"})] == ["d2#0"]
    assert store.nearest([1.0, 0.0], model="m1", limit=5, document_ids=set()) == []


def test_nearest_rejects_non_positive_limit(store: VectorStore):
    with pytest.raises(ValueError):
        store.nearest([1.0, 0.0], model="m1", limit=0)


def test_chunk_belonging_to_other_document_is_rejected(store: VectorStore):
    with pytest.raises(ValueError):
        store.replace_document(_doc("d1"), [_chunk("d2", 0, [1.0, 0.0])])


def test_in_memory_and_sql_stores_satisfy_the_protocol():
    assert isinstance(InMemoryStore(), VectorStore)
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    try:
        assert isinstance(SqlStore(engine), VectorStore)
    finally:
        engine.dispose()


# --- SQL specifics ----------------------------------------------------------------------------------


def test_sql_store_tables_use_rag_prefix_and_own_metadata():
    assert set(RagBase.metadata.tables) == {"rag_documents", "rag_chunks"}


def test_sqlite_store_reports_no_pgvector_and_stores_embedding_as_json():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    try:
        sql_store = SqlStore(engine)
        assert sql_store.uses_pgvector is False
        ddl = str(CreateTable(ChunkRow.__table__).compile(dialect=engine.dialect))
        assert "embedding JSON" in ddl
    finally:
        engine.dispose()


def test_postgres_ddl_uses_pgvector_when_package_is_importable():
    ddl = str(CreateTable(ChunkRow.__table__).compile(dialect=postgresql.dialect()))
    if store_module.PgVector is not None:
        assert "embedding VECTOR(384)" in ddl
    else:  # pragma: no cover - depende do ambiente
        assert "embedding JSON" in ddl


def test_pgvector_nearest_statement_uses_cosine_distance_operator():
    stmt = nearest_statement_pgvector([0.1] * 384, model="m1", limit=5, ids=["d1"])
    sql = str(stmt.compile(dialect=postgresql.dialect()))
    assert "<=>" in sql
    assert "ORDER BY" in sql
    assert "LIMIT" in sql


def test_sql_store_round_trips_chunk_heading_path_and_vector_as_floats():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    try:
        sql_store = SqlStore(engine)
        sql_store.create_schema()
        sql_store.replace_document(_doc("d1"), [_chunk("d1", 0, [0.5, 0.25])])
        [chunk] = sql_store.iter_chunks()
        assert chunk.heading_path == ("Tarifas", "Chaco")
        [(cid, sim)] = sql_store.nearest([0.5, 0.25], model="m1", limit=1)
        assert cid == "d1#0"
        assert sim == pytest.approx(1.0)
    finally:
        engine.dispose()
