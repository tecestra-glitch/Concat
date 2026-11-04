from tests.conftest import add_source, seed_market


def test_health_reports_mode_and_db(client):
    r = client.get("/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["data_mode"] == "real" and body["db"] == "ok" and body["version"]


def test_sources_and_branches(client, db):
    assert client.get("/v1/sources").json() == []
    seed_market(db)
    r = client.get("/v1/sources")
    assert r.status_code == 200
    ids = [s["id"] for s in r.json()]
    assert ids == sorted(ids) and "chaco" in ids and "wu" in ids
    chaco = next(s for s in r.json() if s["id"] == "chaco")
    assert chaco["coverage"] == {"cities": ["CDE", "ASU"], "currencies": ["USD", "BRL", "PYG"]}
    assert chaco["data_mode"] == "real" and chaco["health"] == "ok"
    r = client.get("/v1/sources/chaco/branches")
    assert [b["city"] for b in r.json()] == ["ASU", "CDE"]
    assert client.get("/v1/sources/nope/branches").status_code == 404


def test_sources_expose_integration_seal(client, db):
    add_source(db, "chaco", method="official_api", integration="endpoint_interno")
    add_source(db, "wu", method="browser", integration="navegador")
    by_id = {s["id"]: s for s in client.get("/v1/sources").json()}
    assert by_id["chaco"]["integration"] == "endpoint_interno"
    assert by_id["wu"]["integration"] == "navegador"
    spec = client.get("/openapi.json").json()
    prop = spec["components"]["schemas"]["SourceOut"]["properties"]["integration"]
    assert set(prop["enum"]) == {"api_oficial", "endpoint_interno", "html", "navegador"}


def test_openapi_title_and_mcp_operations(client, app):
    spec = client.get("/openapi.json").json()
    assert spec["info"]["title"] == "Fronteira FX API"
    op_ids = {op["operationId"] for path in spec["paths"].values() for op in path.values()}
    for name in (
        "list_sources",
        "get_quotes",
        "request_quote",
        "get_history",
        "compare_routes",
        "simulate_cycle",
        "search_evidence",
    ):
        assert name in op_ids
    tools = [t.name for t in app.state.mcp.tools]
    contract_tools = {
        "list_sources",
        "get_quotes",
        "request_quote",
        "get_history",
        "compare_routes",
        "simulate_cycle",
        "find_cycles",
        "search_evidence",
        "watch_status",
        "list_changes",
        "trigger_poll",
        "list_alert_rules",
        "create_alert_rule",
        "search_knowledge",
        "remember",
        "recall",
        "forget",
        "memory_summary",
    }
    assert set(tools) == contract_tools and len(tools) == len(contract_tools)
    assert any(getattr(r, "path", "") == "/mcp" for r in app.routes)
