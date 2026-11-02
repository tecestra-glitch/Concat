"""Memória do agente: notas duráveis (preferências, decisões, fatos, resultados) com busca e expiração.

Módulos: `models` (pydantic), `store` (Protocol, InMemoryStore, SqlStore), `service` (regras),
`router` (REST `/v1/memory`, montado pelo core).
"""

from .models import Memory, MemoryCreate, MemoryKind, MemorySource, MemorySummary
from .service import MemoryService
from .store import InMemoryStore, MemoryBase, MemoryStore, SqlStore, create_memory_tables

__all__ = [
    "InMemoryStore",
    "Memory",
    "MemoryBase",
    "MemoryCreate",
    "MemoryKind",
    "MemorySource",
    "MemoryService",
    "MemoryStore",
    "MemorySummary",
    "SqlStore",
    "create_memory_tables",
]
