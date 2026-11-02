"""Regras da memória: gravar (com TTL), buscar, esquecer e resumir para o contexto do agente."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from .models import Memory, MemoryCreate, MemoryKind, MemorySource
from .store import MemoryStore

DEFAULT_LIMIT = 20
MAX_LIMIT = 100
DEFAULT_SUMMARY_LIMIT = 5
SUMMARY_ITEM_CHARS = 200

# Ordem e rótulos do bloco de resumo (pt-BR).
SUMMARY_SECTIONS: tuple[tuple[MemoryKind, str], ...] = (
    ("preference", "Preferências"),
    ("decision", "Decisões"),
    ("fact", "Fatos"),
    ("outcome", "Resultados"),
)


def utc_now() -> datetime:
    return datetime.now(UTC)


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _shorten(text: str, limit: int = SUMMARY_ITEM_CHARS) -> str:
    flat = " ".join(text.split())
    if len(flat) <= limit:
        return flat
    return flat[: limit - 1].rstrip() + "…"


class MemoryService:
    """Fachada usada pelo router REST e pelas ferramentas MCP. `clock` é injetável (TTL nos testes)."""

    def __init__(self, store: MemoryStore, *, clock: Callable[[], datetime] = utc_now) -> None:
        self._store = store
        self._clock = clock

    def remember(self, data: MemoryCreate, *, source: MemorySource = "user") -> Memory:
        now = self._clock()
        expires_at = now + timedelta(days=data.ttl_days) if data.ttl_days is not None else None
        memory = Memory(
            id=str(uuid.uuid4()),
            kind=data.kind,
            text=data.text,
            tags=list(data.tags),
            created_at=now,
            expires_at=expires_at,
            source=source,
        )
        self._store.add(memory)
        return memory

    def recall(
        self,
        *,
        q: str | None = None,
        kind: MemoryKind | None = None,
        tag: str | None = None,
        limit: int = DEFAULT_LIMIT,
    ) -> list[Memory]:
        if not 1 <= limit <= MAX_LIMIT:
            raise ValueError(f"limit deve estar entre 1 e {MAX_LIMIT}")
        return self._store.recall(q=_clean(q), kind=kind, tag=_clean(tag), limit=limit, now=self._clock())

    def forget(self, memory_id: str) -> bool:
        """Remove uma memória. Retorna False se não existe (ou já expirou)."""
        return self._store.delete(memory_id, now=self._clock())

    def purge_expired(self) -> int:
        return self._store.purge_expired(now=self._clock())

    def summarize(self, limit: int = DEFAULT_SUMMARY_LIMIT) -> str:
        """Bloco compacto, uma linha por seção com itens:

        Preferências: a; b
        Decisões: c
        Fatos: d
        Resultados: e

        `limit` é o máximo de itens por seção (mais recentes primeiro). Sem memórias ativas, retorna "".
        """
        if not 1 <= limit <= MAX_LIMIT:
            raise ValueError(f"limit deve estar entre 1 e {MAX_LIMIT}")
        now = self._clock()
        lines: list[str] = []
        for kind, label in SUMMARY_SECTIONS:
            items = self._store.recall(kind=kind, limit=limit, now=now)
            if items:
                lines.append(f"{label}: " + "; ".join(_shorten(m.text) for m in items))
        return "\n".join(lines)
