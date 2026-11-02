from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fronteira_fx.rag.embeddings import EmbeddingError, HashEmbedder
from fronteira_fx.rag.router import get_service, router
from fronteira_fx.rag.service import RagService
from fronteira_fx.rag.store import InMemoryStore


class BrokenEmbedder:
    name = "broken"
    dimensions = 384

    def embed(self, texts):
        raise EmbeddingError("provedor fora do ar")


def _app(service: RagService) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_service] = lambda: service
    return app


@pytest.fixture
def client() -> Iterator[TestClient]:
    service = RagService(InMemoryStore(), HashEmbedder())
    with TestClient(_app(service)) as c:
        yield c


def _post(client: TestClient, **overrides):
    body = {
        "title": "Cambios Chaco",
        "text": "## Horários\nAbre às 8h na filial central.\n\n## Tarifas\nSem taxa pública identificada.",
        "source": "https://www.cambioschaco.com.py/",
        "tags": ["cde", "balcao"],
    }
    body.update(overrides)
    return client.post("/v1/rag/documents", json=body)


def test_post_document_returns_id_and_chunks(client: TestClient):
    response = _post(client)
    assert response.status_code == 201
    payload = response.json()
    assert set(payload) == {"id", "chunks"}
    assert payload["chunks"] >= 1


def test_post_document_rejects_missing_source(client: TestClient):
    body = {"title": "T", "text": "texto", "tags": []}
    assert client.post("/v1/rag/documents", json=body).status_code == 422


def test_post_document_rejects_unknown_fields(client: TestClient):
    assert _post(client, extra="nope").status_code == 422


def test_post_document_rejects_blank_title_or_text(client: TestClient):
    assert _post(client, title="").status_code == 422
    assert _post(client, text="").status_code == 422


def test_post_document_with_only_whitespace_text_is_a_validation_error(client: TestClient):
    response = _post(client, text="   ")
    assert response.status_code == 422


def test_search_returns_contract_shape(client: TestClient):
    _post(client)
    response = client.get("/v1/rag/search", params={"q": "horário Chaco", "k": 3})
    assert response.status_code == 200
    hits = response.json()
    assert hits
    assert set(hits[0]) == {"id", "document_id", "title", "snippet", "score", "source", "tags"}
    assert hits[0]["title"] == "Cambios Chaco"
    assert hits[0]["tags"] == ["cde", "balcao"]


def test_search_default_k_and_tag_filter(client: TestClient):
    _post(client)
    _post(client, title="Outra", tags=["pjc"], source="https://outra.example")
    all_hits = client.get("/v1/rag/search", params={"q": "filial"}).json()
    assert len(all_hits) == 2
    filtered = client.get("/v1/rag/search", params={"q": "filial", "tag": "pjc"}).json()
    assert [h["title"] for h in filtered] == ["Outra"]


@pytest.mark.parametrize(
    "params",
    [{}, {"q": ""}, {"q": "x", "k": 0}, {"q": "x", "k": 51}, {"q": "x" * 501}],
)
def test_search_validates_query_parameters(client: TestClient, params):
    assert client.get("/v1/rag/search", params=params).status_code == 422


def test_list_documents_summary(client: TestClient):
    assert client.get("/v1/rag/documents").json() == []
    _post(client)
    [doc] = client.get("/v1/rag/documents").json()
    assert set(doc) == {"id", "title", "source", "tags", "chunks", "created_at"}
    assert doc["title"] == "Cambios Chaco"
    assert doc["chunks"] >= 1


def test_openapi_operation_ids_match_contract():
    app = _app(RagService(InMemoryStore(), HashEmbedder()))
    paths = app.openapi()["paths"]
    assert paths["/v1/rag/documents"]["post"]["operationId"] == "rag_add_document"
    assert paths["/v1/rag/search"]["get"]["operationId"] == "search_knowledge"
    assert paths["/v1/rag/documents"]["get"]["operationId"] == "rag_list_documents"


def test_embedding_failure_is_503_on_write_and_search():
    store = InMemoryStore()
    RagService(store, HashEmbedder()).add_document("T", "texto sobre taxa", "s")  # busca só chega ao embedder com dados
    with TestClient(_app(RagService(store, BrokenEmbedder()))) as broken:
        assert _post(broken).status_code == 503
        response = broken.get("/v1/rag/search", params={"q": "taxa"})
        assert response.status_code == 503


def test_default_service_factory_is_a_singleton():
    assert get_service() is get_service()
