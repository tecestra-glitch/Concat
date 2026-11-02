"""Rotas /v1/memory em um FastAPI avulso (TestClient), com o serviço de teste injetado via get_service."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fronteira_fx.memory.router import get_service, router
from fronteira_fx.memory.service import MemoryService

from .conftest import T0, FakeClock


@pytest.fixture
def api(service: MemoryService) -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_service] = lambda: service
    with TestClient(app) as client:
        yield client


def test_operation_ids_are_the_mcp_tool_names(api: TestClient) -> None:
    spec = api.get("/openapi.json").json()
    ops = {
        (method, path): body["operationId"]
        for path, methods in spec["paths"].items()
        for method, body in methods.items()
    }
    assert ops[("post", "/v1/memory")] == "remember"
    assert ops[("get", "/v1/memory")] == "recall"
    assert ops[("delete", "/v1/memory/{memory_id}")] == "forget"
    assert ops[("get", "/v1/memory/summary")] == "memory_summary"


def test_post_returns_201_with_contract_shape(api: TestClient) -> None:
    response = api.post(
        "/v1/memory",
        json={
            "kind": "decision",
            "text": "não usar Nomad acima de US$ 1.000 sem confirmar IOF",
            "tags": ["Nomad"],
            "ttl_days": 30,
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert list(body) == ["id", "kind", "text", "tags", "created_at", "expires_at", "source"]
    assert body["kind"] == "decision"
    assert body["tags"] == ["nomad"]
    assert body["source"] == "user"
    created = datetime.fromisoformat(body["created_at"])
    expires = datetime.fromisoformat(body["expires_at"])
    assert created == T0
    assert expires - created == timedelta(days=30)


def test_post_without_ttl_has_null_expiry(api: TestClient) -> None:
    body = api.post("/v1/memory", json={"kind": "fact", "text": "ueno cobra IOF"}).json()
    assert body["expires_at"] is None
    assert body["tags"] == []


def test_post_agent_header_sets_source(api: TestClient) -> None:
    response = api.post(
        "/v1/memory",
        json={"kind": "outcome", "text": "remessa WU CDE->ueno levou 2 dias"},
        headers={"X-Memory-Source": "agent"},
    )
    assert response.json()["source"] == "agent"


@pytest.mark.parametrize(
    "payload",
    [
        {"kind": "opinion", "text": "x"},
        {"kind": "fact", "text": "   "},
        {"kind": "fact", "text": "x", "ttl_days": 0},
    ],
)
def test_post_validates_body(api: TestClient, payload: dict) -> None:
    assert api.post("/v1/memory", json=payload).status_code == 422


def test_post_rejects_unknown_source_header(api: TestClient) -> None:
    response = api.post("/v1/memory", json={"kind": "fact", "text": "x"}, headers={"X-Memory-Source": "robot"})
    assert response.status_code == 422


def test_get_searches_ranks_and_filters(api: TestClient, clock: FakeClock) -> None:
    api.post("/v1/memory", json={"kind": "fact", "text": "Ueno cobra IOF no cartão de crédito", "tags": ["ueno"]})
    clock.advance(minutes=1)
    api.post(
        "/v1/memory", json={"kind": "decision", "text": "Nomad cartão virtual só com confirmação", "tags": ["nomad"]}
    )
    clock.advance(minutes=1)
    api.post("/v1/memory", json={"kind": "preference", "text": "Alberdi PJC acima de R$ 25 mil"})

    ranked = api.get("/v1/memory", params={"q": "ueno cartão"}).json()
    assert [m["tags"] for m in ranked] == [["ueno"], ["nomad"]]

    decisions = api.get("/v1/memory", params={"kind": "decision"}).json()
    assert [m["kind"] for m in decisions] == ["decision"]

    tagged = api.get("/v1/memory", params={"tag": "UENO"}).json()
    assert [m["kind"] for m in tagged] == ["fact"]

    recent = api.get("/v1/memory").json()
    assert [m["kind"] for m in recent] == ["preference", "decision", "fact"]

    assert len(api.get("/v1/memory", params={"limit": 2}).json()) == 2


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"kind": "opinion"}])
def test_get_validates_params(api: TestClient, params: dict) -> None:
    assert api.get("/v1/memory", params=params).status_code == 422


def test_delete_then_404(api: TestClient) -> None:
    memory_id = api.post("/v1/memory", json={"kind": "fact", "text": "x"}).json()["id"]

    first = api.delete(f"/v1/memory/{memory_id}")
    assert first.status_code == 204
    assert first.content == b""

    second = api.delete(f"/v1/memory/{memory_id}")
    assert second.status_code == 404
    assert second.json() == {"detail": "memória não encontrada"}


def test_expired_memory_is_gone_from_recall_and_delete(api: TestClient, clock: FakeClock) -> None:
    memory_id = api.post("/v1/memory", json={"kind": "fact", "text": "promo", "ttl_days": 1}).json()["id"]
    clock.advance(days=1)
    assert api.get("/v1/memory").json() == []
    assert api.delete(f"/v1/memory/{memory_id}").status_code == 404


def test_summary_route(api: TestClient) -> None:
    api.post("/v1/memory", json={"kind": "preference", "text": "prefere Pix para receber"})
    api.post("/v1/memory", json={"kind": "fact", "text": "ueno cobra IOF"})
    assert api.get("/v1/memory/summary").json() == {
        "summary": "Preferências: prefere Pix para receber\nFatos: ueno cobra IOF"
    }


def test_summary_route_empty_and_limit(api: TestClient) -> None:
    assert api.get("/v1/memory/summary").json() == {"summary": ""}
    assert api.get("/v1/memory/summary", params={"limit": 0}).status_code == 422
