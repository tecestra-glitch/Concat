"""Parâmetro `mode` das rotas de oportunidades e ciclos: `celular` é o padrão; `todos` inclui o presencial."""

from __future__ import annotations


def test_mode_defaults_to_celular_and_accepts_todos(client) -> None:
    assert client.get("/v1/opportunities").status_code == 200
    assert client.get("/v1/opportunities", params={"mode": "todos"}).status_code == 200
    assert client.get("/v1/opportunities/cycles").status_code == 200
    assert client.get("/v1/opportunities/cycles", params={"mode": "todos"}).status_code == 200


def test_mode_rejects_unknown_values(client) -> None:
    assert client.get("/v1/opportunities", params={"mode": "presencial"}).status_code == 422
    assert client.get("/v1/opportunities/cycles", params={"mode": "qualquer"}).status_code == 422


def test_openapi_documents_mode_on_both_routes(client) -> None:
    spec = client.get("/openapi.json").json()
    for path in ("/v1/opportunities", "/v1/opportunities/cycles"):
        params = {p["name"]: p for p in spec["paths"][path]["get"]["parameters"]}
        assert params["mode"]["schema"]["enum"] == ["celular", "todos"] or params["mode"]["schema"].get("$ref")
        assert params["mode"]["required"] is False
