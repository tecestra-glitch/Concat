"""Rotas HTTP do RAG (`/v1/rag/...`), conforme docs/api-contract.md.

- POST /v1/rag/documents  -> rag_add_document    body {title, text, source, tags[], metadata?} -> {id, chunks}
- GET  /v1/rag/search     -> search_knowledge    ?q=&k=5&tag=
                             -> [{id, document_id, title, snippet, score, source, tags}]
- GET  /v1/rag/documents  -> rag_list_documents  resumo dos documentos

O serviço vem de `get_service()`. O núcleo sobrescreve essa dependência com `app.dependency_overrides`
(ex.: um RagService com SqlStore). Autenticação das rotas de escrita fica a cargo do núcleo, ao incluir
o roteador com `dependencies=[...]`. Sem sobrescrita, usa um serviço em memória (perde dados ao reiniciar).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from .embeddings import EmbeddingError, get_embedder
from .service import RagService
from .store import InMemoryStore

router = APIRouter(prefix="/v1/rag", tags=["rag"])

_default_service: RagService | None = None


def get_service() -> RagService:
    """Fábrica do serviço padrão (em memória, com o embedder escolhido pelo ambiente)."""
    global _default_service
    if _default_service is None:
        _default_service = RagService(InMemoryStore(), get_embedder())
    return _default_service


ServiceDep = Annotated[RagService, Depends(get_service)]


class AddDocumentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=300)
    text: str = Field(min_length=1, max_length=500_000)
    source: str = Field(min_length=1, max_length=500)
    tags: list[str] = Field(default_factory=list, max_length=20)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AddDocumentOut(BaseModel):
    id: str
    chunks: int


class SearchHitOut(BaseModel):
    id: str
    document_id: str
    title: str
    snippet: str
    score: float
    source: str
    tags: list[str]


class DocumentOut(BaseModel):
    id: str
    title: str
    source: str
    tags: list[str]
    chunks: int
    created_at: datetime


@router.post(
    "/documents",
    response_model=AddDocumentOut,
    status_code=status.HTTP_201_CREATED,
    operation_id="rag_add_document",
    summary="Adiciona um documento à base de conhecimento",
)
def rag_add_document(body: AddDocumentIn, service: ServiceDep) -> AddDocumentOut:
    try:
        doc_id, chunks = service.add_document(body.title, body.text, body.source, body.tags, body.metadata)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    except EmbeddingError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    return AddDocumentOut(id=doc_id, chunks=chunks)


@router.get(
    "/search",
    response_model=list[SearchHitOut],
    operation_id="search_knowledge",
    summary="Busca trechos de documentação, tarifas, horários e evidências",
)
def search_knowledge(
    service: ServiceDep,
    q: Annotated[str, Query(min_length=1, max_length=500)],
    k: Annotated[int, Query(ge=1, le=50)] = 5,
    tag: Annotated[str | None, Query(max_length=40)] = None,
) -> list[SearchHitOut]:
    try:
        hits = service.search(q, k=k, tag=tag)
    except EmbeddingError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    return [
        SearchHitOut(
            id=hit.chunk_id,
            document_id=hit.document_id,
            title=hit.title,
            snippet=hit.snippet,
            score=hit.score,
            source=hit.source,
            tags=list(hit.tags),
        )
        for hit in hits
    ]


@router.get(
    "/documents",
    response_model=list[DocumentOut],
    operation_id="rag_list_documents",
    summary="Lista os documentos da base de conhecimento",
)
def rag_list_documents(service: ServiceDep) -> list[DocumentOut]:
    return [
        DocumentOut(
            id=doc.id,
            title=doc.title,
            source=doc.source,
            tags=list(doc.tags),
            chunks=doc.chunk_count,
            created_at=doc.created_at,
        )
        for doc in service.list_documents()
    ]
