"""Carrega e valida os goldens (casos de avaliação) de `evals/goldens/*.json`.

Cada golden é um caso: a pergunta (`input`), uma resposta de referência (`expected_output`), as ferramentas
MCP que o agente deve chamar (`expected_tools` + `tool_policy`), o retorno de ferramenta usado como
evidência (`tool_output`, snapshot reproduzível) e uma rubrica (`rubric`) com as checagens determinísticas.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fronteira_fx.mcp import MCP_OPERATIONS

EVALS_DIR = Path(__file__).resolve().parent
GOLDENS_DIR = EVALS_DIR / "goldens"
SAMPLES_DIR = EVALS_DIR / "samples"

TASKS = ("quote_answer", "route_explanation", "ranking_rule", "refusal_limit", "parser_repair")
TOOL_POLICIES = ("subset", "exact", "none", "any")
CONFIDENCES = (None, "quoted", "estimated", "incomplete")
RUBRIC_KEYS = frozenset(
    {
        "must_include",
        "must_include_any",
        "must_include_numbers",
        "must_not_include_numbers",
        "must_not_match",
        "numbers_must_be_sourced",
        "ignore_numbers",
        "json_equals",
        "forbidden_tools",
    }
)
# Pelo menos uma destas checagens de conteúdo precisa existir, senão o golden não testa nada.
CONTENT_CHECK_KEYS = frozenset({"must_include", "must_include_any", "must_include_numbers", "json_equals"})
# Tarefas em que a resposta depende de um retorno de ferramenta (snapshot obrigatório).
NEEDS_TOOL_OUTPUT = frozenset({"quote_answer", "route_explanation", "ranking_rule"})
REQUIRED_KEYS = ("id", "task", "lang", "input", "expected_output", "expected_tools", "tool_policy", "rubric", "tags")


@dataclass(frozen=True)
class ExpectedTool:
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Golden:
    id: str
    task: str
    input: str
    expected_output: str
    expected_tools: tuple[ExpectedTool, ...]
    tool_policy: str
    rubric: dict[str, Any]
    tags: tuple[str, ...]
    tool_output: Any = None
    confidence: str | None = None
    source: str = ""


def validate_golden(raw: Any, source: str = "") -> list[str]:
    """Devolve a lista de erros de um golden bruto (vazia quando válido)."""
    where = f"{source}:{raw.get('id', '?')}" if isinstance(raw, dict) else source
    if not isinstance(raw, dict):
        return [f"{where}: golden precisa ser um objeto JSON"]
    errors = [f"{where}: campo obrigatório ausente '{key}'" for key in REQUIRED_KEYS if key not in raw]
    if errors:
        return errors

    def bad(msg: str) -> None:
        errors.append(f"{where}: {msg}")

    if not isinstance(raw["id"], str) or not raw["id"].strip():
        bad("id precisa ser texto não vazio")
    if raw["task"] not in TASKS:
        bad(f"task inválida {raw['task']!r}; use {TASKS}")
    if raw["lang"] != "pt-BR":
        bad("lang precisa ser 'pt-BR'")
    for key in ("input", "expected_output"):
        if not isinstance(raw[key], str) or not raw[key].strip():
            bad(f"{key} precisa ser texto não vazio")
    if not isinstance(raw["tags"], list) or not raw["tags"] or not all(isinstance(t, str) for t in raw["tags"]):
        bad("tags precisa ser uma lista não vazia de textos")

    policy = raw["tool_policy"]
    if policy not in TOOL_POLICIES:
        bad(f"tool_policy inválida {policy!r}; use {TOOL_POLICIES}")
    tools = raw["expected_tools"]
    if not isinstance(tools, list):
        bad("expected_tools precisa ser uma lista")
        tools = []
    for tool in tools:
        if not isinstance(tool, dict) or tool.get("name") not in MCP_OPERATIONS:
            bad(f"ferramenta esperada desconhecida: {tool!r} (válidas: {', '.join(MCP_OPERATIONS)})")
        elif not isinstance(tool.get("arguments", {}), dict):
            bad(f"arguments de {tool['name']} precisa ser um objeto")
    if policy == "none" and tools:
        bad("tool_policy 'none' exige expected_tools vazio")
    if policy in ("subset", "exact") and not tools:
        bad(f"tool_policy {policy!r} exige pelo menos uma ferramenta esperada")

    if raw.get("confidence") not in CONFIDENCES:
        bad(f"confidence inválida {raw.get('confidence')!r}")

    rubric = raw["rubric"]
    if not isinstance(rubric, dict):
        bad("rubric precisa ser um objeto")
        return errors
    unknown = set(rubric) - RUBRIC_KEYS
    if unknown:
        bad(f"chaves de rubrica desconhecidas: {sorted(unknown)}")
    if not (set(rubric) & CONTENT_CHECK_KEYS):
        bad("rubric sem checagem de conteúdo (must_include, must_include_any, must_include_numbers ou json_equals)")
    if rubric.get("numbers_must_be_sourced") and raw.get("tool_output") is None:
        bad("numbers_must_be_sourced exige tool_output")
    for name in rubric.get("forbidden_tools", []):
        if name not in MCP_OPERATIONS:
            bad(f"forbidden_tools cita ferramenta desconhecida {name!r}")

    if raw["task"] in NEEDS_TOOL_OUTPUT and raw.get("tool_output") is None:
        bad(f"task {raw['task']!r} exige tool_output (snapshot do retorno da ferramenta)")
    if raw["task"] == "parser_repair":
        if "json_equals" not in rubric:
            bad("parser_repair exige rubric.json_equals")
        if policy != "none":
            bad("parser_repair não usa ferramentas: tool_policy deve ser 'none'")
    return errors


def parse_golden(raw: dict[str, Any], source: str = "") -> Golden:
    return Golden(
        id=raw["id"],
        task=raw["task"],
        input=raw["input"],
        expected_output=raw["expected_output"],
        expected_tools=tuple(
            ExpectedTool(name=t["name"], arguments=dict(t.get("arguments", {}))) for t in raw["expected_tools"]
        ),
        tool_policy=raw["tool_policy"],
        rubric=dict(raw["rubric"]),
        tags=tuple(raw["tags"]),
        tool_output=raw.get("tool_output"),
        confidence=raw.get("confidence"),
        source=source,
    )


def load_goldens_file(path: Path) -> list[Golden]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"{path.name}: o arquivo precisa ser uma lista de goldens")
    errors: list[str] = []
    goldens: list[Golden] = []
    for item in raw:
        item_errors = validate_golden(item, path.name)
        if item_errors:
            errors.extend(item_errors)
        else:
            goldens.append(parse_golden(item, path.name))
    if errors:
        raise ValueError("\n".join(errors))
    return goldens


def load_goldens(directory: Path = GOLDENS_DIR) -> list[Golden]:
    goldens: list[Golden] = []
    for path in sorted(directory.glob("*.json")):
        goldens.extend(load_goldens_file(path))
    seen: set[str] = set()
    for golden in goldens:
        if golden.id in seen:
            raise ValueError(f"id de golden duplicado: {golden.id}")
        seen.add(golden.id)
    return goldens


def golden_index(goldens: list[Golden]) -> dict[str, Golden]:
    return {g.id: g for g in goldens}
