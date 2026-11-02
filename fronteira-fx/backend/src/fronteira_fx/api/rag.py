from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, status

from ..schemas import RagDocumentCreate, RagDocumentCreated, RagDocumentOut, RagHit
from ..services import rag as rag_svc
from .deps import ApiKey, DataModeDep, DbDep

router = APIRouter(prefix="/rag", tags=["rag"])


@router.post("/documents", operation_id="add_knowledge", status_code=status.HTTP_201_CREATED, dependencies=[ApiKey])
def add_document(body: RagDocumentCreate, db: DbDep, data_mode: DataModeDep) -> RagDocumentCreated:
    doc = rag_svc.add_document(db, body, data_mode=data_mode)
    return RagDocumentCreated(id=doc.id, chunks=rag_svc.chunk_count(db, doc.id))


@router.get("/documents", operation_id="list_knowledge")
def list_documents(db: DbDep, data_mode: DataModeDep) -> list[RagDocumentOut]:
    return rag_svc.list_documents(db, data_mode=data_mode)


@router.get("/search", operation_id="search_knowledge", summary="Lexical search over the knowledge corpus")
def search(
    db: DbDep,
    data_mode: DataModeDep,
    q: Annotated[str, Query(min_length=1, max_length=500)],
    k: Annotated[int, Query(ge=1, le=50)] = 5,
    tag: Annotated[str | None, Query(max_length=64)] = None,
) -> list[RagHit]:
    return rag_svc.search(db, q, k=k, tag=tag, data_mode=data_mode)
