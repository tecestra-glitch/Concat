"""MCP server mounted at /mcp (fastapi-mcp). Only the contract's tools are exposed."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi_mcp import FastApiMCP

MCP_OPERATIONS: list[str] = [
    # core
    "list_sources",
    "get_quotes",
    "request_quote",
    "get_history",
    "compare_routes",
    "simulate_cycle",
    "find_cycles",
    "search_evidence",
    # watch
    "watch_status",
    "list_changes",
    "trigger_poll",
    # notify
    "list_alert_rules",
    "create_alert_rule",
    # rag
    "search_knowledge",
    # memory
    "remember",
    "recall",
    "forget",
    "memory_summary",
]


def mount_mcp(app: FastAPI, mount_path: str = "/mcp") -> FastApiMCP:
    mcp = FastApiMCP(
        app,
        name="Fronteira FX MCP",
        description="Cotações BRL/USD/PYG, rotas e evidências do terminal Fronteira FX.",
        include_operations=list(MCP_OPERATIONS),
        headers=["authorization", "x-api-key"],
    )
    mcp.mount_http(mount_path=mount_path)
    return mcp
