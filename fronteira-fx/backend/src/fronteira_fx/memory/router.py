"""Rotas REST `/v1/memory`. Os `operation_id` viram as ferramentas MCP `remember`, `recall`, `forget`
e `memory_summary` quando o core as expõe via fastapi-mcp.

O core monta assim (autenticação e serviço real ficam com ele):

    app.include_router(memory_router, dependencies=[ApiKey])
    app.dependency_overrides[get_service] = lambda: MemoryService(SqlStore(app.state.session_factory))

Origem: POST grava `source="user"`, a não ser que a chamada traga `X-Memory-Source: agent`
(o caminho MCP do agente deve enviar esse header).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status

from .models import Memory, MemoryCreate, MemoryKind, MemorySource, MemorySummary
from .service import DEFAULT_LIMIT, DEFAULT_SUMMARY_LIMIT, MAX_LIMIT, MemoryService
from .store import InMemoryStore

router = APIRouter(prefix="/v1/memory", tags=["memory"])

_default_service: MemoryService | None = None


def get_service() -> MemoryService:
    """Fábrica do serviço. Sem override, usa `InMemoryStore` (some ao reiniciar): o core deve sobrescrever."""
    global _default_service
    if _default_service is None:
        _default_service = MemoryService(InMemoryStore())
    return _default_service


ServiceDep = Annotated[MemoryService, Depends(get_service)]
SourceHeader = Annotated[MemorySource, Header(alias="X-Memory-Source")]


@router.post(
    "",
    operation_id="remember",
    status_code=status.HTTP_201_CREATED,
    response_model=Memory,
)
def remember(body: MemoryCreate, service: ServiceDep, source: SourceHeader = "user") -> Memory:
    return service.remember(body, source=source)


@router.get("", operation_id="recall", response_model=list[Memory])
def recall(
    service: ServiceDep,
    q: Annotated[str | None, Query(max_length=500)] = None,
    kind: MemoryKind | None = None,
    tag: Annotated[str | None, Query(max_length=40)] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
) -> list[Memory]:
    return service.recall(q=q, kind=kind, tag=tag, limit=limit)


@router.get("/summary", operation_id="memory_summary", response_model=MemorySummary)
def memory_summary(
    service: ServiceDep,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_SUMMARY_LIMIT,
) -> MemorySummary:
    return MemorySummary(summary=service.summarize(limit=limit))


@router.delete("/{memory_id}", operation_id="forget", status_code=status.HTTP_204_NO_CONTENT)
def forget(memory_id: str, service: ServiceDep) -> None:
    if not service.forget(memory_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="memória não encontrada")
