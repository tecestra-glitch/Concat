"""GET /v1/institutions: cadastro estático de instituições, sem banco e sem `data_mode` próprio."""

from __future__ import annotations

from fastapi.testclient import TestClient

from fronteira_fx.main import create_app
from fronteira_fx.mcp import MCP_OPERATIONS
from tests.conftest import make_settings


def test_lists_all_institutions_with_provenance():
    app = create_app(make_settings(), mount_mcp_server=False)
    with TestClient(app) as c:
        resp = c.get("/v1/institutions")
    assert resp.status_code == 200
    rows = resp.json()
    by_id = {row["id"]: row for row in rows}
    assert len(rows) == 25
    assert by_id["ueno"]["status"] == "discontinued"
    assert by_id["nubank-conta-global"]["fx_cost"]["iof_pct"]["value"] == "0.035"
    assert by_id["nubank-conta-global"]["fx_cost"]["iof_pct"]["source_url"].startswith("https://")
    assert by_id["c6-conta-global"]["fx_cost"]["iof_pct"]["value"] is None


def test_money_is_serialized_as_string_not_number():
    app = create_app(make_settings(), mount_mcp_server=False)
    with TestClient(app) as c:
        rows = {row["id"]: row for row in c.get("/v1/institutions").json()}
    assert rows["basa"]["fx_cost"]["spread_pct"]["value"] == "0.0592"
    assert isinstance(rows["basa"]["fx_cost"]["spread_pct"]["value"], str)


def test_operation_is_in_spec_and_mcp():
    app = create_app(make_settings(), mount_mcp_server=False)
    ids = {op["operationId"] for ops in app.openapi()["paths"].values() for op in ops.values()}
    assert "list_institutions" in ids
    assert "list_institutions" in MCP_OPERATIONS
