"""Obtém a resposta do agente para cada golden: ao vivo (contra a API/MCP) ou por replay gravado.

Modos (escolhidos por variável de ambiente, nesta ordem):
  * FX_EVAL_RUNS=caminho.json  -> replay: lista de {golden_id, answer, tool_calls, tool_outputs}.
  * FX_EVAL_AGENT=modulo:funcao -> chama `funcao(pergunta, mcp_url)` e espera um dict com
    `answer`, `tool_calls` ([{name, arguments}]) e `tool_outputs` ([texto]). É o ponto onde se liga o agente real
    (por exemplo, um cliente de LLM com o servidor MCP de `FX_API_URL/mcp` configurado).

Sem nenhum dos dois, `run_agent` levanta `NotConfigured` e o teste é pulado (não falha).
"""

from __future__ import annotations

import importlib
import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx

ENV_API_URL = "FX_API_URL"
ENV_AGENT = "FX_EVAL_AGENT"
ENV_RUNS = "FX_EVAL_RUNS"
DEFAULT_API_URL = "http://localhost:8000"


class NotConfigured(Exception):
    """Falta configuração para executar o agente. Os testes tratam como skip."""


@dataclass(frozen=True)
class AgentRun:
    answer: str
    tool_calls: tuple[dict[str, Any], ...] = ()
    tool_outputs: tuple[str, ...] = ()


def api_base_url() -> str:
    return os.environ.get(ENV_API_URL, DEFAULT_API_URL).rstrip("/")


def mcp_url() -> str:
    return f"{api_base_url()}/mcp"


def api_is_up(timeout: float = 3.0) -> bool:
    try:
        response = httpx.get(f"{api_base_url()}/v1/health", timeout=timeout)
    except httpx.HTTPError:
        return False
    return response.status_code == 200


@lru_cache(maxsize=4)
def _load_replays(path: str) -> dict[str, AgentRun]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return {
        item["golden_id"]: AgentRun(
            answer=item["answer"],
            tool_calls=tuple(item.get("tool_calls", [])),
            tool_outputs=tuple(item.get("tool_outputs", [])),
        )
        for item in raw
    }


def _resolve(spec: str):
    module_name, _, func_name = spec.partition(":")
    if not module_name or not func_name:
        raise NotConfigured(f"{ENV_AGENT} deve ter o formato modulo:funcao (recebido {spec!r})")
    return getattr(importlib.import_module(module_name), func_name)


def run_agent(question_id: str, question: str) -> AgentRun:
    replay = os.environ.get(ENV_RUNS)
    if replay:
        runs = _load_replays(replay)
        if question_id not in runs:
            raise NotConfigured(f"{ENV_RUNS} não tem execução para {question_id}")
        return runs[question_id]

    spec = os.environ.get(ENV_AGENT)
    if not spec:
        raise NotConfigured(f"defina {ENV_AGENT}=modulo:funcao ou {ENV_RUNS}=arquivo.json (ver docs)")
    if not api_is_up():
        raise NotConfigured(f"a API não responde em {api_base_url()}/v1/health (suba o backend ou ajuste {ENV_API_URL})")
    result = _resolve(spec)(question, mcp_url())
    return AgentRun(
        answer=str(result["answer"]),
        tool_calls=tuple(result.get("tool_calls", [])),
        tool_outputs=tuple(str(o) for o in result.get("tool_outputs", [])),
    )
