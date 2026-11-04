"""docs/openapi.json é o contrato OpenAPI exportado: tem de bater com o que o app gera agora (paridade).
Também confere que toda rota de conexões aparece em docs/api-contract.md."""

from __future__ import annotations

import json
from pathlib import Path

from fronteira_fx.config import Settings
from fronteira_fx.main import create_app

DOCS = Path(__file__).resolve().parents[3] / "docs"
OPENAPI_FILE = DOCS / "openapi.json"
CONTRACT_FILE = DOCS / "api-contract.md"


def _app():
    return create_app(Settings(_env_file=None, database_url="sqlite://", auto_create_schema=False))


def test_committed_openapi_matches_app() -> None:
    committed = json.loads(OPENAPI_FILE.read_text(encoding="utf-8"))
    assert committed == json.loads(json.dumps(_app().openapi())), "rode: uv run python scripts/export_openapi.py"


def test_every_connection_route_is_documented_in_contract() -> None:
    contract = CONTRACT_FILE.read_text(encoding="utf-8")
    routes = [p for p in _app().openapi()["paths"] if p.startswith("/v1/connections")]
    assert len(routes) == 6
    for route in routes:
        doc_form = route.replace("{connection_id}", "{id}")
        assert doc_form in contract, f"rota {route} sem entrada em docs/api-contract.md"
