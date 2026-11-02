"""Rubricas determinísticas (offline, sem LLM) e definições DeepEval opcionais para os goldens.

Parte offline: `run_rubric` confere, numa resposta do agente, o que o golden exige:
  * ferramentas MCP chamadas (política `tool_policy` + `forbidden_tools`);
  * frases obrigatórias (normalizadas: sem acento, minúsculas);
  * números em pt-BR ou en (`7.290`, `7290`, `1.363,79`, `0,85%` ...), com a mesma regra de porcentagem;
  * números proibidos (perspectiva errada, por exemplo);
  * números que não existem no retorno da ferramenta (`numbers_must_be_sourced`);
  * afirmações proibidas, como "lucro confirmado" ou execução já realizada, ignorando frases negadas
    ("não é lucro confirmado" passa; "lucro confirmado de 42 reais" falha);
  * JSON com campo esperado (classificação do parser).

Parte DeepEval: `to_test_case` e `build_metrics` só funcionam com `deepeval` instalado; o import é adiado
e pulado com `pytest.importorskip` quando o pacote não existe.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

import pytest

from .dataset import Golden
from .runner import AgentRun

# ---------------------------------------------------------------------------------------------------
# Texto e frases
# ---------------------------------------------------------------------------------------------------


def normalize(text: str) -> str:
    """Minúsculas, sem acentos e com espaços colapsados. Usado em todas as comparações de texto."""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", stripped.lower()).strip()


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?;])\s+|\n+")
_NEGATION = re.compile(r"\b(nao|nunca|jamais|nem|nenhum|nenhuma)\b")


def sentences(normalized_text: str) -> list[str]:
    return [s for s in _SENTENCE_SPLIT.split(normalized_text) if s.strip()]


# ---------------------------------------------------------------------------------------------------
# Números
# ---------------------------------------------------------------------------------------------------

_NUM_TOKEN = re.compile(r"\d+(?:[.,]\d+)*")
# "1 p.p.", "0 %", "2 dias", "100%" não são evidência de nada; ficam fora da checagem de origem.
_TRIVIAL = frozenset(Decimal(v) for v in ("0", "1", "2", "3", "100"))


def _dec(text: str) -> Decimal | None:
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def candidate_numbers(token: str) -> set[Decimal]:
    """Interpretações possíveis de um token numérico.

    Um mesmo token pode ser pt-BR ("7.290" = 7290, "5,372" = 5,372) ou en ("5.372" = 5,372). Por isso
    o token gera todas as leituras plausíveis e basta uma delas bater.
    """
    out: set[Decimal] = set()
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?", token):  # pt-BR: 1.363,79 / 7.290
        value = _dec(token.replace(".", "").replace(",", "."))
        if value is not None:
            out.add(value)
    if re.fullmatch(r"\d+,\d+", token):  # pt-BR decimal: 0,85
        value = _dec(token.replace(",", "."))
        if value is not None:
            out.add(value)
    if re.fullmatch(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?", token):  # en com milhar: 1,363.79
        value = _dec(token.replace(",", ""))
        if value is not None:
            out.add(value)
    if re.fullmatch(r"\d+(?:\.\d+)?", token):  # en / simples: 7290, 5.372
        value = _dec(token)
        if value is not None:
            out.add(value)
    return out


def _places(value: Decimal) -> int:
    return max(0, -value.normalize().as_tuple().exponent)


def _equal_or_percent(candidate: Decimal, expected: Decimal) -> bool:
    """Aceita o número como valor, como porcentagem (0,85% = 0.0085) ou em módulo (sinal ignorado)."""
    base = abs(expected)
    return abs(candidate) in {base, base * 100, base / 100}


def _sourced(candidate: Decimal, source_values: set[Decimal]) -> bool:
    """O candidato aparece no retorno da ferramenta, arredondado na mesma precisão, em valor ou porcentagem."""
    for variant in (candidate, candidate / 100, candidate * 100):
        places = _places(variant)
        quantum = Decimal(1).scaleb(-places)
        target = abs(variant).quantize(quantum)
        if any(abs(s).quantize(quantum) == target for s in source_values):
            return True
    return False


def _numbers_in_json(payload: Any) -> set[Decimal]:
    text = json.dumps(payload, ensure_ascii=False, default=str)
    values: set[Decimal] = set()
    for token in _NUM_TOKEN.findall(text):
        values |= candidate_numbers(token)
    return values


# ---------------------------------------------------------------------------------------------------
# Afirmações proibidas (globais: valem para todos os goldens)
# ---------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Claim:
    id: str
    pattern: re.Pattern[str]
    description: str


FORBIDDEN_CLAIMS: tuple[Claim, ...] = (
    Claim(
        "lucro_confirmado",
        re.compile(r"\b(lucro|ganho|resultado)s?\s+(confirmad[oa]s?|certos?|garantid[oa]s?)\b"),
        "Apresentar estimativa como lucro confirmado (regra: incomplete nunca é lucro confirmado).",
    ),
    Claim(
        "garantia_de_retorno",
        re.compile(r"\bgarant(o|imos|ido|ida)\b|\b(lucro|ganho|retorno)\b.*\bgarantid[oa]s?\b|\bsem\s+risco\b"),
        "Prometer ganho ou retorno garantido.",
    ),
    Claim(
        "execucao_realizada",
        re.compile(
            r"\b(executei|transferi|enviei\s+(o\s+|a\s+)?(dinheiro|valor|pix|transferencia)"
            r"|(transferencia|operacao|ordem)\s+(foi\s+|ja\s+)?(realizad[ao]|executad[ao]|concluid[ao]|enviad[ao]|iniciad[ao]))\b"
        ),
        "Afirmar que uma movimentação foi executada. O terminal não executa nada nesta fase.",
    ),
)


def claim_violations(normalized_text: str) -> list[str]:
    """Ids das afirmações proibidas presentes em frases que não são negadas."""
    found: list[str] = []
    for claim in FORBIDDEN_CLAIMS:
        for sentence in sentences(normalized_text):
            if claim.pattern.search(sentence) and not _NEGATION.search(sentence):
                found.append(claim.id)
                break
    return found


# ---------------------------------------------------------------------------------------------------
# Rubrica
# ---------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Check:
    id: str
    ok: bool
    detail: str = ""


@dataclass(frozen=True)
class RubricReport:
    golden_id: str
    checks: tuple[Check, ...]

    @property
    def passed(self) -> bool:
        return all(c.ok for c in self.checks)

    @property
    def failed_ids(self) -> list[str]:
        return [c.id for c in self.checks if not c.ok]


def _args_match(actual: dict[str, Any], expected: dict[str, Any]) -> bool:
    for key, value in expected.items():
        if key not in actual or actual[key] is None:
            return False
        if str(actual[key]).strip().lower() != str(value).strip().lower():
            return False
    return True


def _json_object(answer: str) -> dict[str, Any] | None:
    match = re.search(r"\{.*\}", answer, re.DOTALL)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _tool_checks(golden: Golden, calls: list[dict[str, Any]]) -> list[Check]:
    names = [str(c.get("name", "")) for c in calls]
    checks: list[Check] = []
    policy = golden.tool_policy
    if policy == "none":
        checks.append(Check("tool.policy", not names, f"chamadas: {names or 'nenhuma'}"))
    elif policy == "exact":
        expected = sorted({t.name for t in golden.expected_tools})
        checks.append(Check("tool.policy", sorted(set(names)) == expected, f"chamadas: {sorted(set(names))}"))
    elif policy == "subset":
        for tool in golden.expected_tools:
            matched = any(
                c.get("name") == tool.name and _args_match(c.get("arguments") or {}, tool.arguments) for c in calls
            )
            checks.append(Check(f"tool.call:{tool.name}", matched, f"esperado {tool.arguments or 'sem argumentos'}"))
    for forbidden in golden.rubric.get("forbidden_tools", []):
        checks.append(Check(f"tool.forbidden:{forbidden}", forbidden not in names))
    return checks


def run_rubric(golden: Golden, answer: str, tool_calls: list[dict[str, Any]] | None = None) -> RubricReport:
    """Confere a resposta do agente contra a rubrica do golden. Não chama nenhum modelo."""
    calls = list(tool_calls or [])
    rubric = golden.rubric
    text = normalize(answer)
    checks: list[Check] = _tool_checks(golden, calls)

    for phrase in rubric.get("must_include", []):
        checks.append(Check(f"phrase:{phrase}", normalize(phrase) in text))
    for index, group in enumerate(rubric.get("must_include_any", [])):
        hit = any(normalize(p) in text for p in group)
        checks.append(Check(f"any[{index}]", hit, f"uma de {group}"))

    tokens = _NUM_TOKEN.findall(text)
    token_values = {token: candidate_numbers(token) for token in tokens}
    all_values = set().union(*token_values.values()) if token_values else set()
    for expected in rubric.get("must_include_numbers", []):
        value = _dec(str(expected))
        found = value is not None and any(_equal_or_percent(c, value) for c in all_values)
        checks.append(Check(f"number.include:{expected}", found))
    for excluded in rubric.get("must_not_include_numbers", []):
        value = _dec(str(excluded))
        found = value is not None and any(abs(c) == abs(value) for c in all_values)
        checks.append(Check(f"number.exclude:{excluded}", not found))

    for pattern in rubric.get("must_not_match", []):
        checks.append(Check(f"regex:{pattern}", re.search(pattern, text, re.IGNORECASE) is None))

    if rubric.get("numbers_must_be_sourced"):
        ignored = set(_TRIVIAL) | {Decimal(str(v)) for v in rubric.get("ignore_numbers", [])}
        source_values = _numbers_in_json(golden.tool_output)
        for token, candidates in token_values.items():
            if not candidates or any(abs(c) in ignored for c in candidates):
                continue
            ok = any(_sourced(c, source_values) for c in candidates)
            checks.append(Check(f"number.sourced:{token}", ok, "não aparece no retorno da ferramenta"))

    violated = set(claim_violations(text))
    for claim in FORBIDDEN_CLAIMS:
        if claim.id in violated:
            checks.append(Check(f"claim:{claim.id}", False, claim.description))
        else:
            checks.append(Check(f"claim:{claim.id}", True))

    if "json_equals" in rubric:
        payload = _json_object(answer)
        if payload is None:
            checks.append(Check("json.parse", False, "resposta sem objeto JSON válido"))
        for key, expected in rubric.get("json_equals", {}).items():
            actual = "" if payload is None else payload.get(key, "")
            ok = payload is not None and normalize(str(actual)) == normalize(str(expected))
            checks.append(Check(f"json.equals:{key}", ok, f"esperado {expected!r}, veio {actual!r}"))

    return RubricReport(golden_id=golden.id, checks=tuple(checks))


def expected_calls(golden: Golden) -> list[dict[str, Any]]:
    """Chamadas que a própria referência faria: útil para checar que o golden passa na sua rubrica."""
    return [{"name": t.name, "arguments": dict(t.arguments)} for t in golden.expected_tools]


# ---------------------------------------------------------------------------------------------------
# DeepEval (opcional): mesmos goldens, métricas de juiz
# ---------------------------------------------------------------------------------------------------

FAITHFULNESS_CRITERIA = (
    "A resposta só afirma preços, taxas, datas, quantidades e status que aparecem no retorno das "
    "ferramentas (retrieval_context). Penalize qualquer valor inventado, valor arredondado de forma que mude "
    "o sentido, e qualquer afirmação sem fonte no retorno."
)
PRODUCT_RULES_CRITERIA = (
    "Verifique as regras do produto: (1) taxa efetiva = crédito líquido / débito total; "
    "(2) um físico só entra no ranking principal com ROI pelo menos 1 ponto percentual acima do melhor digital "
    "comparável; (3) estimativa incompleta (custos pendentes) nunca é apresentada como lucro confirmado e os "
    "custos pendentes são citados; (4) o terminal não executa movimentações: a resposta deve deixar claro que a "
    "execução não está habilitada e que a fase é de aprovação; (5) dados de demonstração são sinalizados como "
    "ilustrativos. Compare com a resposta de referência (expected_output)."
)


def to_test_case(golden: Golden, run: AgentRun) -> Any:
    """Converte golden + execução do agente em `LLMTestCase` do DeepEval. Requer `deepeval`."""
    pytest.importorskip("deepeval")
    from deepeval.test_case import LLMTestCase, ToolCall

    called = [
        ToolCall(name=str(c["name"]), input_parameters=dict(c.get("arguments") or {})) for c in run.tool_calls
    ]
    expected = [ToolCall(name=t.name, input_parameters=dict(t.arguments)) for t in golden.expected_tools]
    return LLMTestCase(
        input=golden.input,
        actual_output=run.answer,
        expected_output=golden.expected_output,
        retrieval_context=list(run.tool_outputs) or None,
        tools_called=called or None,
        expected_tools=expected or None,
    )


def build_metrics(golden: Golden, *, threshold: float = 0.7) -> list[Any]:
    """Métricas DeepEval para um golden. Novas instâncias a cada chamada (são stateful). Requer `deepeval`."""
    pytest.importorskip("deepeval")
    from deepeval.metrics import AnswerRelevancyMetric, GEval, ToolCorrectnessMetric
    from deepeval.test_case import SingleTurnParams as P

    metrics: list[Any] = [
        GEval(
            name="Regras do produto",
            evaluation_params=[P.INPUT, P.ACTUAL_OUTPUT, P.EXPECTED_OUTPUT],
            criteria=PRODUCT_RULES_CRITERIA,
            threshold=threshold,
        ),
        AnswerRelevancyMetric(threshold=threshold),
    ]
    if golden.tool_output is not None:
        # Fidelidade só faz sentido quando há retorno de ferramenta para comparar.
        metrics.append(
            GEval(
                name="Fidelidade ao retorno das ferramentas",
                evaluation_params=[P.INPUT, P.ACTUAL_OUTPUT, P.RETRIEVAL_CONTEXT],
                criteria=FAITHFULNESS_CRITERIA,
                threshold=threshold,
            )
        )
    if golden.expected_tools:
        metrics.append(ToolCorrectnessMetric(threshold=threshold))
    return metrics
