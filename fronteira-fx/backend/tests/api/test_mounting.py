"""B12: every route reaches the app through `api.v1_router`; the module routers (`memory/router.py`,
`notify/router.py`, `graph/router.py`, `rag/router.py`, `watch/router.py`) are reference implementations and
are never mounted, so no `operationId` is duplicated and no module-only operation leaks into the spec."""

from __future__ import annotations

from fronteira_fx.main import create_app
from fronteira_fx.mcp import MCP_OPERATIONS
from tests.conftest import make_settings

# 36 operations when the plan was written + `memory_summary` (B10). Bump deliberately when adding an endpoint.
EXPECTED_OPERATIONS = 37
MODULE_ONLY_OPERATIONS = {"rag_add_document", "rag_list_documents", "watch_update_source"}


def _operations(app) -> list[tuple[str, str, str]]:
    return [
        (path, method, op["operationId"])
        for path, ops in app.openapi()["paths"].items()
        for method, op in ops.items()
    ]


def test_all_operations_live_under_v1_without_duplicates():
    app = create_app(make_settings(), mount_mcp_server=False)
    ops = _operations(app)
    assert ops, "spec has no operations"
    assert all(path.startswith("/v1/") for path, _, _ in ops), [p for p, _, _ in ops if not p.startswith("/v1/")]
    ids = [op_id for _, _, op_id in ops]
    duplicated = {i for i in ids if ids.count(i) > 1}
    assert not duplicated, f"operationId duplicado: {sorted(duplicated)}"
    assert len(ids) == EXPECTED_OPERATIONS, sorted(ids)
    assert not MODULE_ONLY_OPERATIONS & set(ids), "um router de módulo foi montado em create_app()"


def test_mcp_operations_exist_in_the_spec():
    app = create_app(make_settings(), mount_mcp_server=False)
    ids = {op_id for _, _, op_id in _operations(app)}
    missing = set(MCP_OPERATIONS) - ids
    assert not missing, f"MCP expõe operações que não existem: {sorted(missing)}"
    assert len(MCP_OPERATIONS) == len(set(MCP_OPERATIONS)) == 18
