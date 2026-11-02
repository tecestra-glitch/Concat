"""Modelos pydantic da memória do agente (contrato "Memória do agente" em docs/api-contract.md).

Uma memória é uma nota curta e durável: preferência do usuário, decisão tomada, fato sobre um provedor
ou resultado de uma operação passada. `source` diz quem gravou ("user" ou "agent").
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

MemoryKind = Literal["preference", "decision", "fact", "outcome"]
MemorySource = Literal["user", "agent"]

MAX_TEXT_CHARS = 2000
MAX_TAG_CHARS = 40
MAX_TAGS = 20
MAX_TTL_DAYS = 3650

MemoryText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_TEXT_CHARS)]
MemoryTag = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_TAG_CHARS)]


def normalize_tags(tags: Iterable[str]) -> list[str]:
    """Minúsculas, sem repetidas, na ordem de chegada."""
    unique: dict[str, None] = {}
    for tag in tags:
        unique.setdefault(tag.lower(), None)
    return list(unique)


class MemoryCreate(BaseModel):
    """Corpo de `POST /v1/memory`."""

    kind: MemoryKind
    text: MemoryText
    tags: list[MemoryTag] = Field(default_factory=list, max_length=MAX_TAGS)
    ttl_days: int | None = Field(default=None, ge=1, le=MAX_TTL_DAYS)

    @field_validator("tags", mode="after")
    @classmethod
    def _normalize_tags(cls, value: list[str]) -> list[str]:
        return normalize_tags(value)


class Memory(BaseModel):
    """Objeto `Memory` do contrato. Datas em UTC; `expires_at` é null quando não expira."""

    model_config = ConfigDict(frozen=True)

    id: str
    kind: MemoryKind
    text: str
    tags: list[str]
    created_at: datetime
    expires_at: datetime | None = None
    source: MemorySource


class MemorySummary(BaseModel):
    """Resposta de `GET /v1/memory/summary`: bloco compacto em pt-BR para injetar no contexto do agente."""

    summary: str
