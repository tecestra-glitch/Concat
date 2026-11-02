from __future__ import annotations

import json
import math
import os
import subprocess
import sys
from pathlib import Path

import httpx
import pytest
import respx

from fronteira_fx.rag.embeddings import (
    EMBEDDING_DIM,
    EmbeddingError,
    HashEmbedder,
    OpenAICompatibleEmbedder,
    cosine,
    get_embedder,
)

BACKEND = Path(__file__).resolve().parents[2]
ENDPOINT = "https://emb.example.test/v1/embeddings"


# --- HashEmbedder ---------------------------------------------------------------------------------


def test_hash_embedder_produces_384_dim_unit_vectors():
    [vector] = HashEmbedder().embed(["taxa efetiva do câmbio em remessas"])
    assert len(vector) == EMBEDDING_DIM == 384
    assert math.isclose(math.sqrt(sum(x * x for x in vector)), 1.0, rel_tol=1e-9)


def test_hash_embedder_empty_text_is_zero_vector():
    [vector] = HashEmbedder().embed([""])
    assert vector == [0.0] * EMBEDDING_DIM


def test_hash_embedder_is_deterministic_within_process():
    a = HashEmbedder().embed(["horário Chaco", "taxa efetiva"])
    b = HashEmbedder().embed(["horário Chaco", "taxa efetiva"])
    assert a == b


def test_hash_embedder_is_deterministic_across_processes_with_different_hash_seeds():
    code = (
        "import json, sys; sys.path.insert(0, 'src');"
        "from fronteira_fx.rag.embeddings import HashEmbedder;"
        "print(json.dumps(HashEmbedder(64).embed(['horário Chaco taxa efetiva'])))"
    )
    outputs = []
    for seed in ("1", "2"):
        env = {**os.environ, "PYTHONHASHSEED": seed}
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=BACKEND,
            env=env,
            capture_output=True,
            text=True,
            check=True,
            timeout=60,
        )
        outputs.append(json.loads(result.stdout))
    assert outputs[0] == outputs[1]


def test_accents_and_plurals_map_to_the_same_vector():
    emb = HashEmbedder()
    accented, plain = emb.embed(["horário"]), emb.embed(["horarios"])
    assert accented == plain


def test_related_text_is_closer_than_unrelated_text():
    emb = HashEmbedder()
    query, related, unrelated = emb.embed(
        ["tarifa da Western Union", "Western Union taxa de transferência", "clima chuvoso em Asunción"]
    )
    assert cosine(query, related) > cosine(query, unrelated)


def test_hash_embedder_rejects_tiny_dimensions():
    with pytest.raises(ValueError):
        HashEmbedder(dimensions=4)


def test_cosine_basic_properties():
    assert cosine([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert cosine([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)
    assert cosine([0.0, 0.0], [1.0, 0.0]) == 0.0
    with pytest.raises(ValueError):
        cosine([1.0], [1.0, 0.0])


# --- OpenAICompatibleEmbedder (respx) --------------------------------------------------------------


@respx.mock
def test_openai_compatible_request_shape_and_result_order():
    route = respx.post(ENDPOINT).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {"index": 1, "embedding": [0.0, 3.0, 0.0, 0.0]},
                    {"index": 0, "embedding": [4.0, 0.0, 0.0, 0.0]},
                ]
            },
        )
    )
    emb = OpenAICompatibleEmbedder("https://emb.example.test/v1/", "text-embedding-test", api_key="sekret", dimensions=4)

    vectors = emb.embed(["primeiro", "segundo"])

    assert vectors == [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]]  # ordenado por index e normalizado
    request = route.calls.last.request
    assert request.headers["Authorization"] == "Bearer sekret"
    body = json.loads(request.content)
    assert body == {"model": "text-embedding-test", "input": ["primeiro", "segundo"]}  # sem "dimensions" por padrão


@respx.mock
def test_dimensions_field_is_sent_only_when_configured():
    route = respx.post(ENDPOINT).mock(
        return_value=httpx.Response(200, json={"data": [{"index": 0, "embedding": [1.0, 0.0, 0.0, 0.0]}]})
    )
    emb = OpenAICompatibleEmbedder(
        "https://emb.example.test/v1", "m", dimensions=4, send_dimensions=True
    )
    emb.embed(["x"])
    assert json.loads(route.calls.last.request.content)["dimensions"] == 4


@respx.mock
def test_requests_are_batched():
    def handler(request: httpx.Request) -> httpx.Response:
        count = len(json.loads(request.content)["input"])
        return httpx.Response(200, json={"data": [{"index": i, "embedding": [1.0, 0.0, 0.0, 0.0]} for i in range(count)]})

    route = respx.post(ENDPOINT).mock(side_effect=handler)
    emb = OpenAICompatibleEmbedder("https://emb.example.test/v1", "m", dimensions=4, batch_size=2)
    vectors = emb.embed([f"t{i}" for i in range(5)])
    assert len(vectors) == 5
    assert route.call_count == 3  # 2 + 2 + 1


@respx.mock
def test_empty_input_makes_no_request():
    route = respx.post(ENDPOINT).mock(return_value=httpx.Response(200, json={"data": []}))
    emb = OpenAICompatibleEmbedder("https://emb.example.test/v1", "m", dimensions=4)
    assert emb.embed([]) == []
    assert route.call_count == 0


@respx.mock
def test_http_error_becomes_embedding_error():
    respx.post(ENDPOINT).mock(return_value=httpx.Response(500, text="boom"))
    emb = OpenAICompatibleEmbedder("https://emb.example.test/v1", "m", dimensions=4)
    with pytest.raises(EmbeddingError, match="HTTP 500"):
        emb.embed(["x"])


@respx.mock
def test_network_error_becomes_embedding_error():
    respx.post(ENDPOINT).mock(side_effect=httpx.ConnectError("sem rota"))
    emb = OpenAICompatibleEmbedder("https://emb.example.test/v1", "m", dimensions=4)
    with pytest.raises(EmbeddingError, match="falha de rede"):
        emb.embed(["x"])


@respx.mock
def test_non_json_response_becomes_embedding_error():
    respx.post(ENDPOINT).mock(return_value=httpx.Response(200, text="<html>"))
    emb = OpenAICompatibleEmbedder("https://emb.example.test/v1", "m", dimensions=4)
    with pytest.raises(EmbeddingError, match="não é JSON"):
        emb.embed(["x"])


@respx.mock
def test_wrong_vector_count_becomes_embedding_error():
    respx.post(ENDPOINT).mock(return_value=httpx.Response(200, json={"data": [{"index": 0, "embedding": [1, 0, 0, 0]}]}))
    emb = OpenAICompatibleEmbedder("https://emb.example.test/v1", "m", dimensions=4)
    with pytest.raises(EmbeddingError, match="1 vetores para 2 textos"):
        emb.embed(["a", "b"])


@respx.mock
def test_wrong_dimension_becomes_embedding_error():
    respx.post(ENDPOINT).mock(return_value=httpx.Response(200, json={"data": [{"index": 0, "embedding": [1, 0]}]}))
    emb = OpenAICompatibleEmbedder("https://emb.example.test/v1", "m", dimensions=4)
    with pytest.raises(EmbeddingError, match="2 dimensões, esperado 4"):
        emb.embed(["a"])


@respx.mock
def test_duplicated_index_becomes_embedding_error():
    respx.post(ENDPOINT).mock(
        return_value=httpx.Response(
            200,
            json={"data": [{"index": 0, "embedding": [1, 0, 0, 0]}, {"index": 0, "embedding": [0, 1, 0, 0]}]},
        )
    )
    emb = OpenAICompatibleEmbedder("https://emb.example.test/v1", "m", dimensions=4)
    with pytest.raises(EmbeddingError, match="índice"):
        emb.embed(["a", "b"])


def test_constructor_validates_arguments():
    with pytest.raises(ValueError):
        OpenAICompatibleEmbedder(" ", "m")
    with pytest.raises(ValueError):
        OpenAICompatibleEmbedder("https://x", "m", batch_size=0)


# --- get_embedder ----------------------------------------------------------------------------------


def test_get_embedder_falls_back_to_hash_without_configuration():
    assert isinstance(get_embedder({}), HashEmbedder)


def test_get_embedder_needs_both_base_url_and_model():
    assert isinstance(get_embedder({"FX_EMBEDDINGS_BASE_URL": "http://localhost:11434/v1"}), HashEmbedder)
    assert isinstance(get_embedder({"FX_EMBEDDINGS_MODEL": "all-minilm"}), HashEmbedder)


def test_get_embedder_builds_openai_compatible_client_from_env():
    emb = get_embedder(
        {
            "FX_EMBEDDINGS_BASE_URL": "http://localhost:1234/v1",
            "FX_EMBEDDINGS_MODEL": "all-minilm",
            "FX_EMBEDDINGS_API_KEY": "k",
            "FX_EMBEDDINGS_DIMENSIONS": "384",
        }
    )
    assert isinstance(emb, OpenAICompatibleEmbedder)
    assert emb.name == "openai-compatible:all-minilm"
    assert emb.dimensions == 384
    assert emb._send_dimensions is True  # noqa: SLF001 - dimensão explicitamente configurada é enviada


def test_get_embedder_reads_os_environ_by_default(monkeypatch):
    monkeypatch.setenv("FX_EMBEDDINGS_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setenv("FX_EMBEDDINGS_MODEL", "all-minilm")
    monkeypatch.delenv("FX_EMBEDDINGS_DIMENSIONS", raising=False)
    emb = get_embedder()
    assert isinstance(emb, OpenAICompatibleEmbedder)
    assert emb.dimensions == EMBEDDING_DIM
    assert emb._send_dimensions is False  # noqa: SLF001
