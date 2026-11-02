"""Módulo RAG do Fronteira FX: documentação, tarifas (texto), horários e evidências. Nunca cotações.

Ver docs/rag.md. Pontos de entrada: `RagService`, `get_embedder`, `InMemoryStore` / `SqlStore`
e o roteador `fronteira_fx.rag.router.router`.
"""

from .chunking import Chunk, chunk_text
from .embeddings import Embedder, EmbeddingError, HashEmbedder, OpenAICompatibleEmbedder, get_embedder
from .retriever import SearchHit
from .service import RagService, SeedResult
from .store import ChunkRecord, DocumentRecord, InMemoryStore, RagBase, SqlStore, VectorStore

__all__ = [
    "Chunk",
    "ChunkRecord",
    "DocumentRecord",
    "Embedder",
    "EmbeddingError",
    "HashEmbedder",
    "InMemoryStore",
    "OpenAICompatibleEmbedder",
    "RagBase",
    "RagService",
    "SearchHit",
    "SeedResult",
    "SqlStore",
    "VectorStore",
    "chunk_text",
    "get_embedder",
]
