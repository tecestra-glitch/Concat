"""Embeddings do RAG: protocolo, embedder offline por hashing e cliente para APIs compatíveis com OpenAI.

- `HashEmbedder`: determinístico e sem dependências (blake2b, não o `hash()` do Python, que muda por processo).
  Captura palavras e trigramas de caracteres; não entende sinônimos. Usado em testes e no modo offline.
- `OpenAICompatibleEmbedder`: `POST {base_url}/embeddings`. Serve OpenAI, Ollama e LM Studio.
- `get_embedder()`: escolhe pelo ambiente (FX_EMBEDDINGS_*) e cai para o `HashEmbedder` se faltar configuração.
"""

from __future__ import annotations

import hashlib
import logging
import math
import os
from collections.abc import Mapping, Sequence
from typing import Protocol, runtime_checkable

import httpx

from .text import tokenize

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 384  # dimensão da coluna pgvector vector(384) e padrão do HashEmbedder
_HASH_FEATURE_VERSION = "v1"  # mudar as features muda os vetores: incrementar para invalidar índices antigos


class EmbeddingError(RuntimeError):
    """Falha ao gerar embeddings: rede, HTTP de erro, resposta fora do formato ou dimensão inesperada."""


@runtime_checkable
class Embedder(Protocol):
    name: str
    dimensions: int

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


def l2_normalize(vector: Sequence[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vector))
    if norm == 0.0:
        return [0.0] * len(vector)
    return [x / norm for x in vector]


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if len(a) != len(b):
        raise ValueError("vetores de dimensões diferentes")
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return sum(x * y for x, y in zip(a, b, strict=True)) / (norm_a * norm_b)


def _hash_features(text: str) -> list[tuple[str, float]]:
    features: list[tuple[str, float]] = []
    for token in tokenize(text):
        features.append((f"w:{token}", 1.0))
        padded = f" {token} "
        for i in range(len(padded) - 2):
            features.append((f"c:{padded[i : i + 3]}", 0.5))
    return features


class HashEmbedder:
    """Embedding determinístico por hashing de palavras e trigramas, com sinal, normalizado em L2."""

    def __init__(self, dimensions: int = EMBEDDING_DIM) -> None:
        if dimensions < 8:
            raise ValueError("dimensions deve ser >= 8")
        self.dimensions = dimensions
        self.name = f"hash-{_HASH_FEATURE_VERSION}-{dimensions}"

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for feature, weight in _hash_features(text):
            digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "little") % self.dimensions
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[index] += sign * weight
        return l2_normalize(vector)


class OpenAICompatibleEmbedder:
    """Cliente de `POST {base_url}/embeddings` (formato OpenAI). Lotes de `batch_size` textos por requisição."""

    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        api_key: str | None = None,
        dimensions: int = EMBEDDING_DIM,
        send_dimensions: bool = False,
        timeout: float = 30.0,
        batch_size: int = 64,
        client: httpx.Client | None = None,
    ) -> None:
        if not base_url.strip() or not model.strip():
            raise ValueError("base_url e model são obrigatórios")
        if batch_size < 1:
            raise ValueError("batch_size deve ser >= 1")
        self.model = model.strip()
        self.name = f"openai-compatible:{self.model}"
        self.dimensions = dimensions
        self._endpoint = base_url.strip().rstrip("/") + "/embeddings"
        self._api_key = api_key
        self._send_dimensions = send_dimensions  # só envia o campo `dimensions` se foi configurado explicitamente
        self._batch_size = batch_size
        self._owns_client = client is None
        self._client = client if client is not None else httpx.Client(timeout=timeout)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        items = list(texts)
        vectors: list[list[float]] = []
        for start in range(0, len(items), self._batch_size):
            vectors.extend(self._embed_batch(items[start : start + self._batch_size]))
        return vectors

    def _embed_batch(self, batch: list[str]) -> list[list[float]]:
        payload: dict[str, object] = {"model": self.model, "input": batch}
        if self._send_dimensions:
            payload["dimensions"] = self.dimensions
        headers = {"Accept": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        try:
            response = self._client.post(self._endpoint, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            raise EmbeddingError(f"falha de rede ao chamar embeddings ({exc.__class__.__name__})") from exc
        if response.status_code >= 400:
            raise EmbeddingError(f"embeddings respondeu HTTP {response.status_code}: {response.text[:200]}")
        try:
            body = response.json()
        except ValueError as exc:
            raise EmbeddingError("resposta de embeddings não é JSON") from exc
        return self._parse(body, expected=len(batch))

    def _parse(self, body: object, *, expected: int) -> list[list[float]]:
        data = body.get("data") if isinstance(body, dict) else None
        if not isinstance(data, list) or len(data) != expected:
            got = len(data) if isinstance(data, list) else "?"
            raise EmbeddingError(f"embeddings devolveu {got} vetores para {expected} textos")
        by_index: dict[int, list[float]] = {}
        for position, item in enumerate(data):
            if not isinstance(item, dict) or not isinstance(item.get("embedding"), list):
                raise EmbeddingError("item de embeddings sem campo 'embedding'")
            index = item.get("index", position)
            if not isinstance(index, int) or not 0 <= index < expected or index in by_index:
                raise EmbeddingError("índice de embedding inválido ou repetido")
            try:
                vector = [float(x) for x in item["embedding"]]
            except (TypeError, ValueError) as exc:
                raise EmbeddingError("valor não numérico em 'embedding'") from exc
            if len(vector) != self.dimensions:
                raise EmbeddingError(
                    f"embedding com {len(vector)} dimensões, esperado {self.dimensions}: "
                    "ajuste FX_EMBEDDINGS_DIMENSIONS ou escolha um modelo com essa dimensão"
                )
            by_index[index] = l2_normalize(vector)
        return [by_index[i] for i in range(expected)]


def get_embedder(env: Mapping[str, str] | None = None) -> Embedder:
    """Escolhe o embedder pelo ambiente. Sem FX_EMBEDDINGS_BASE_URL e FX_EMBEDDINGS_MODEL, usa o HashEmbedder.

    Variáveis: FX_EMBEDDINGS_BASE_URL, FX_EMBEDDINGS_MODEL, FX_EMBEDDINGS_API_KEY (opcional),
    FX_EMBEDDINGS_DIMENSIONS (opcional; quando definida, também é enviada à API).
    Não faz chamadas de rede na construção.
    """
    source: Mapping[str, str] = os.environ if env is None else env
    base_url = (source.get("FX_EMBEDDINGS_BASE_URL") or "").strip()
    model = (source.get("FX_EMBEDDINGS_MODEL") or "").strip()
    if base_url and model:
        raw_dims = (source.get("FX_EMBEDDINGS_DIMENSIONS") or "").strip()
        dimensions = int(raw_dims) if raw_dims else EMBEDDING_DIM
        api_key = (source.get("FX_EMBEDDINGS_API_KEY") or "").strip() or None
        logger.info("RAG: embeddings por API compatível (modelo=%s, dimensões=%d)", model, dimensions)
        return OpenAICompatibleEmbedder(
            base_url,
            model,
            api_key=api_key,
            dimensions=dimensions,
            send_dimensions=bool(raw_dims),
        )
    if base_url or model:
        logger.warning("RAG: defina FX_EMBEDDINGS_BASE_URL e FX_EMBEDDINGS_MODEL juntos; usando HashEmbedder")
    return HashEmbedder()
