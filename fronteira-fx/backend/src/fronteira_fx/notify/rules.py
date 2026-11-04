"""Regras de alerta: modelos (contrato `AlertRule` / `AlertEvent`) e avaliação pura, sem I/O.

`evaluate` recebe a regra, o tipo do evento do stream e o payload. Quando a condição vale e o cooldown
permite, devolve um `AlertEvent` ainda não entregue. A entrega fica em `service.py`.

Significado dos limiares (`threshold`, sempre `Decimal`):
- `cycle_roi`: dispara se `roi >= threshold` (roi é fração: `0.002` = 0,2 %).
- `quote_move`: dispara se `|valor / valor_anterior - 1| >= threshold` (razão, não percentual).
  O valor é o ponto médio entre compra e venda da cotação (ou o que existir).
- `opportunity_new`: dispara quando a oportunidade entra no ranking principal e `roi >= threshold`
  (use 0 para qualquer entrada).
- `source_down`: dispara na transição para `blocked` ou `error`; `threshold` não é usado.

Cooldown: depois de disparar, a mesma chave (`dedupe_key`) da mesma regra só volta a disparar quando
passarem `cooldown_s` segundos. A chave é o ciclo (sequência de nós), a série da cotação
(fonte/cidade/par/modalidade/tipo/filial), a fonte ou o id da oportunidade.
"""

from __future__ import annotations

import math
import re
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Annotated, Any, Literal, Self
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, model_validator

from ..decimal_utils import fmt
from . import messages

RuleKind = Literal["cycle_roi", "quote_move", "source_down", "opportunity_new"]
ChannelName = Literal["ui", "telegram", "webhook", "email"]

# Tipos de evento do stream que cada tipo de regra consome.
KIND_EVENTS: dict[str, frozenset[str]] = {
    "cycle_roi": frozenset({"cycle.found"}),
    "quote_move": frozenset({"quote.updated"}),
    "source_down": frozenset({"source.health", "source.change"}),
    "opportunity_new": frozenset({"opportunity.updated"}),
}
BAD_HEALTH: frozenset[str] = frozenset({"blocked", "error"})
CITIES: frozenset[str] = frozenset({"CDE", "ASU", "PJC", "FOZ"})
MAX_COOLDOWN_S = 30 * 86_400

_PAIR_RE = re.compile(r"^[A-Za-z]{3}/[A-Za-z]{3}$")
_TELEGRAM_TARGET_RE = re.compile(r"^(-?\d{1,20}|@[A-Za-z][A-Za-z0-9_]{4,})$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Decimal serializado como string no JSON (contrato: valores monetários e limiares trafegam como string).
DecStr = Annotated[Decimal, PlainSerializer(lambda v: fmt(v, None), return_type=str, when_used="json")]


class AlertRuleIn(BaseModel):
    """Corpo de criação (e base de `AlertRule`): todos os campos da regra, exceto o id."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    kind: RuleKind
    threshold: DecStr
    params: dict[str, Any] | None = None
    channel: ChannelName = "ui"
    target: str | None = Field(default=None, max_length=500)
    cooldown_s: int = Field(default=600, ge=0, le=MAX_COOLDOWN_S)
    enabled: bool = True

    @model_validator(mode="after")
    def _check_rule(self) -> Self:
        if not self.name.strip():
            raise ValueError("name não pode ser vazio")
        self.name = self.name.strip()
        if not self.threshold.is_finite():
            raise ValueError("threshold deve ser um número finito")
        self.params = _normalize_params(self.kind, self.params, self.threshold)
        self.target = _check_target(self.channel, self.target)
        return self


class AlertRule(AlertRuleIn):
    """Regra persistida (contrato `AlertRule`)."""

    id: str


class AlertRulePatch(BaseModel):
    """Corpo de PATCH: só os campos informados mudam."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=120)
    kind: RuleKind | None = None
    threshold: DecStr | None = None
    params: dict[str, Any] | None = None
    channel: ChannelName | None = None
    target: str | None = Field(default=None, max_length=500)
    cooldown_s: int | None = Field(default=None, ge=0, le=MAX_COOLDOWN_S)
    enabled: bool | None = None


class AlertEvent(BaseModel):
    """Disparo de uma regra (contrato `AlertEvent`). `delivered`/`error` refletem a tentativa de envio."""

    id: str
    rule_id: str
    ts: datetime
    message: str
    payload: dict[str, Any] = Field(default_factory=dict)
    channel: ChannelName
    delivered: bool = False
    error: str | None = None


def merge_rule(current: AlertRule, patch: AlertRulePatch) -> AlertRule:
    """Aplica um PATCH e revalida a regra inteira. Levanta `ValidationError` se o resultado for inválido."""
    data = current.model_dump(exclude={"id"})
    data.update(patch.model_dump(exclude_unset=True))
    checked = AlertRuleIn.model_validate(data)
    return AlertRule(id=current.id, **checked.model_dump())


def _normalize_params(kind: str, params: Mapping[str, Any] | None, threshold: Decimal) -> dict[str, Any] | None:
    p: dict[str, Any] = dict(params or {})
    if kind == "quote_move":
        pair = p.get("pair")
        if not isinstance(pair, str) or not _PAIR_RE.match(pair):
            raise ValueError("quote_move exige params.pair no formato 'USD/PYG'")
        if threshold < 0:
            raise ValueError("quote_move: threshold é uma razão e não pode ser negativo")
        p["pair"] = pair.upper()
        city = p.get("city")
        if city is not None and city not in CITIES:
            raise ValueError("params.city deve ser CDE, ASU, PJC, FOZ ou null")
    if kind == "opportunity_new":
        channel = p.get("channel")
        if channel is not None and channel not in ("digital", "physical"):
            raise ValueError("params.channel deve ser digital ou physical")
        city = p.get("city")
        if city is not None and city not in CITIES:
            raise ValueError("params.city deve ser CDE, ASU, PJC, FOZ ou null")
    return p or None


def _check_target(channel: str, target: str | None) -> str | None:
    if channel == "ui":
        return None  # a UI lê o histórico; não há destino externo
    value = (target or "").strip()
    if not value:
        raise ValueError(f"o canal {channel} exige target")
    if channel == "telegram" and not _TELEGRAM_TARGET_RE.match(value):
        raise ValueError("telegram: target deve ser o chat id numérico (ou @nomedocanal)")
    if channel == "email" and not _EMAIL_RE.match(value):
        raise ValueError("email: target deve ser um endereço de e-mail válido")
    if channel == "webhook":
        parts = urlsplit(value)
        if parts.scheme not in ("http", "https") or not parts.netloc:
            raise ValueError("webhook: target deve ser uma URL http(s)")
    return value


@dataclass
class AlertState:
    """Memória entre avaliações, em processo.

    `fired`: (rule_id, dedupe_key) -> instante do último disparo (base do cooldown).
    `previous`: (rule_id, dedupe_key) -> última observação (valor da cotação, saúde da fonte, entrada no ranking).
    """

    fired: dict[tuple[str, str], datetime] = field(default_factory=dict)
    previous: dict[tuple[str, str], Any] = field(default_factory=dict)

    def forget_rule(self, rule_id: str) -> None:
        for mapping in (self.fired, self.previous):
            for slot in [slot for slot in mapping if slot[0] == rule_id]:
                del mapping[slot]


def evaluate(
    rule: AlertRule,
    event_type: str,
    payload: Mapping[str, Any],
    state: AlertState,
    *,
    now: datetime | None = None,
) -> AlertEvent | None:
    """Avalia uma regra contra um evento do stream. Devolve o disparo (não entregue) ou None.

    Atualiza `state` (observações anteriores e instante do disparo). Não faz I/O.
    """
    if event_type not in KIND_EVENTS.get(rule.kind, frozenset()):
        return None
    moment = _aware(now) if now is not None else datetime.now(UTC)
    message = _MATCHERS[rule.kind](rule, event_type, payload, state)
    if message is None:
        return None
    key = dedupe_key(rule, event_type, payload)
    if key is None:
        return None
    slot = (rule.id, key)
    last = state.fired.get(slot)
    if last is not None and rule.cooldown_s > 0 and (moment - last).total_seconds() < rule.cooldown_s:
        return None
    state.fired[slot] = moment
    return AlertEvent(
        id=str(uuid.uuid4()),
        rule_id=rule.id,
        ts=moment,
        message=message,
        payload=_jsonable(payload),
        channel=rule.channel,
    )


def dedupe_key(rule: AlertRule, event_type: str, payload: Mapping[str, Any]) -> str | None:
    """Chave de cooldown: o mesmo ciclo, a mesma série de cotação, a mesma fonte ou a mesma oportunidade."""
    if rule.kind == "cycle_roi":
        path = payload.get("path")
        if isinstance(path, list | tuple) and path:
            return "cycle:" + ">".join(str(node) for node in path)
        start = payload.get("start")
        return f"cycle:{start}" if start else None
    if rule.kind == "quote_move":
        return f"quote:{_series_key(payload)}"
    if rule.kind == "source_down":
        obs = _source_observation(event_type, payload)
        return f"source:{obs.source_id}" if obs else None
    if rule.kind == "opportunity_new":
        opp_id = payload.get("id")
        return f"opp:{opp_id}" if opp_id else None
    return None


# --- matchers: devolvem o texto da mensagem quando a condição vale (sem olhar o cooldown) ---


def _match_cycle_roi(rule: AlertRule, event_type: str, payload: Mapping[str, Any], state: AlertState) -> str | None:
    roi = _dec(payload.get("roi"))
    if roi is None or roi < rule.threshold:
        return None
    path = [str(node) for node in payload.get("path") or []]
    start = str(payload.get("start") or (path[0] if path else ""))
    wanted = (rule.params or {}).get("start")
    if wanted and not start.startswith(str(wanted)):
        return None
    currency = start.split("@", 1)[0].upper()
    return messages.cycle_text(
        path=path or [start],
        gain=_dec(payload.get("gain")) or Decimal(0),
        roi=roi,
        minutes=_dec(payload.get("minutes")) or Decimal(0),
        confidence=str(payload.get("confidence") or "estimated"),
        currency=currency,
    )


def _match_quote_move(rule: AlertRule, event_type: str, payload: Mapping[str, Any], state: AlertState) -> str | None:
    params = rule.params or {}
    if not _quote_matches(params, payload):
        return None
    value = quote_value(payload)
    if value is None:
        return None
    slot = (rule.id, dedupe_key(rule, event_type, payload) or "")
    previous = state.previous.get(slot)
    state.previous[slot] = value  # a referência é sempre a última observação, dispare ou não
    if previous is None or previous <= 0:
        return None
    move = (value - previous) / previous
    if move == 0 or abs(move) < rule.threshold:
        return None
    base, quote = str(payload["base"]), str(payload["quote"])
    return messages.quote_move_text(
        base=base,
        quote=quote,
        city=payload.get("city"),
        source_id=str(payload.get("source_id") or "?"),
        previous=previous,
        current=value,
        ratio=move,
    )


def _match_source_down(rule: AlertRule, event_type: str, payload: Mapping[str, Any], state: AlertState) -> str | None:
    obs = _source_observation(event_type, payload)
    if obs is None:
        return None
    wanted = (rule.params or {}).get("source")
    if wanted and obs.source_id != wanted:
        return None
    slot = (rule.id, f"source:{obs.source_id}")
    previous = state.previous.get(slot)
    state.previous[slot] = obs.health
    if obs.health not in BAD_HEALTH or previous in BAD_HEALTH:
        return None  # só a transição para ruim conta
    return messages.source_down_text(label=obs.label, health=obs.health, detail=obs.detail)


def _match_opportunity_new(
    rule: AlertRule, event_type: str, payload: Mapping[str, Any], state: AlertState
) -> str | None:
    opp_id = payload.get("id")
    if not opp_id:
        return None
    roi = _dec(payload.get("roi"))
    qualifies = (
        payload.get("in_main_ranking") is True
        and roi is not None
        and roi >= rule.threshold
        and _opportunity_matches(rule.params or {}, payload)
    )
    slot = (rule.id, f"opp:{opp_id}")
    previous = state.previous.get(slot, False)
    state.previous[slot] = qualifies
    if not qualifies or previous:
        return None  # dispara só na entrada
    return messages.opportunity_text(
        title=str(payload.get("title") or opp_id),
        net_gain=_dec(payload.get("net_gain_brl")),
        roi=roi,
        capital=_dec(payload.get("capital_brl")),
    )


_MATCHERS: dict[str, Any] = {
    "cycle_roi": _match_cycle_roi,
    "quote_move": _match_quote_move,
    "source_down": _match_source_down,
    "opportunity_new": _match_opportunity_new,
}


# --- helpers de payload ---


@dataclass(frozen=True)
class _SourceObservation:
    source_id: str
    health: str
    label: str
    detail: str | None


def _source_observation(event_type: str, payload: Mapping[str, Any]) -> _SourceObservation | None:
    """Normaliza `source.health` (Source) e `source.change` (Change de status) para (fonte, saúde, texto)."""
    if event_type == "source.change":
        after = payload.get("after")
        after = after if isinstance(after, Mapping) else {}
        health = after.get("health") or after.get("status")
        detail = after.get("last_error") or payload.get("summary")
        name = None
    else:
        health = payload.get("health")
        detail = payload.get("last_error")
        name = payload.get("name")
    source_id = payload.get("source_id") or payload.get("id")
    if not source_id or not isinstance(health, str):
        return None
    source_id = str(source_id)
    label = f"{name} ({source_id})" if name and name != source_id else source_id
    return _SourceObservation(source_id=source_id, health=health, label=label, detail=detail)


def quote_value(quote: Mapping[str, Any]) -> Decimal | None:
    """Valor de referência de uma cotação: ponto médio de compra e venda, ou o lado que existir."""
    buy = _positive(quote.get("buy"))
    sell = _positive(quote.get("sell"))
    if buy is not None and sell is not None:
        return (buy + sell) / 2
    return buy if buy is not None else sell


def _series_key(quote: Mapping[str, Any]) -> str:
    city = quote.get("city") or "digital"
    branch = quote.get("branch_id") or "-"
    return (
        f"{quote.get('source_id')}:{city}:{quote.get('base')}/{quote.get('quote')}"
        f":{quote.get('modality')}:{quote.get('kind')}:{branch}"
    )


def _quote_matches(params: Mapping[str, Any], quote: Mapping[str, Any]) -> bool:
    pair = params.get("pair")
    if not pair or f"{quote.get('base')}/{quote.get('quote')}".upper() != str(pair).upper():
        return False
    for param, field_name in (("city", "city"), ("source", "source_id"), ("modality", "modality")):
        wanted = params.get(param)
        if wanted and quote.get(field_name) != wanted:
            return False
    return True


def _opportunity_matches(params: Mapping[str, Any], opportunity: Mapping[str, Any]) -> bool:
    if params.get("channel") and opportunity.get("channel") != params["channel"]:
        return False
    return not (params.get("city") and opportunity.get("city") != params["city"])


def _dec(value: Any) -> Decimal | None:
    """Converte número ou string decimal; None para ausente, booleano, inválido ou não finito."""
    if value is None or isinstance(value, bool):
        return None
    try:
        out = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return out if out.is_finite() else None


def _positive(value: Any) -> Decimal | None:
    out = _dec(value)
    return out if out is not None and out > 0 else None


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _jsonable(value: Any) -> Any:
    """Converte o payload em estrutura JSON pura (Decimal vira string, datetime vira ISO)."""
    if value is None or isinstance(value, bool | int | str):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if isinstance(value, Decimal):
        return fmt(value, None)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple | set | frozenset):
        return [_jsonable(v) for v in value]
    return str(value)
