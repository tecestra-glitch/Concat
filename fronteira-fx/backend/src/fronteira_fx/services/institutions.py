"""Cadastro de instituições onde o titular abre contas (`data/institutions.json`).

Padrão igual ao de `logistics`: arquivo empacotado, pydantic, `lru_cache`, e qualquer violação vira `ValueError` com o
id da linha. Regras de proveniência:

- todo número de custo (`fx_cost`) carrega `source_url` e `checked_at`; valor `null` = não confirmado (nunca zero);
- fatos não numéricos (`currencies_held`, `opens_remotely`, `requires`, `api`) compartilham a fonte da entrada
  (`source_url` + `checked_at`) e só podem ter valor quando essa fonte existe;
- dinheiro e percentuais entram como string decimal; percentual é fração (`"0.035"` = 3,5 %); número JSON é recusado.
"""

from __future__ import annotations

import json
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from importlib import resources
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

Country = Literal["BR", "PY", "INT"]
"""País em que o titular abre a conta (grupo do levantamento); `INT` para serviços sem país fixo (ex.: Airtm)."""
Kind = Literal["bank", "fintech", "wallet", "broker"]
Status = Literal["active", "discontinued"]
Api = Literal["none", "pf", "pj_contract"]
_ID_RE = re.compile(r"[a-z0-9][a-z0-9_-]{1,63}")
_CODE_RE = re.compile(r"[A-Z]{3,4}")
_CANONICAL_RE = re.compile(r"-?\d+(\.\d+)?")
"""Mesmo formato que `DecimalString` do frontend: sem sinal de mais, espaços ou notação científica."""
_FIXED_CURRENCIES = {"BRL", "USD", "EUR", "PYG", "USDC"}


def _decimal_string(value: Any, field: str) -> Decimal:
    if not isinstance(value, str):
        raise ValueError(f"{field} deve ser string decimal (ex.: \"0.035\"), não número JSON")
    if not _CANONICAL_RE.fullmatch(value):
        raise ValueError(f"{field} deve ser decimal canônico (ex.: \"0.035\"): {value!r}")
    try:
        out = Decimal(value)
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} não é um decimal válido: {value!r}") from None
    if not out.is_finite():
        raise ValueError(f"{field} deve ser finito")
    return out


class Figure(BaseModel):
    """Um número de custo com a sua fonte. `value` null = não confirmado pela pesquisa."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    value: str | None = None
    currency: str | None = None
    source_url: str | None = None
    checked_at: date | None = None
    note: str | None = None

    @field_validator("value", mode="before")
    @classmethod
    def _value(cls, value: Any) -> Any:
        if value is None:
            return None
        _decimal_string(value, "value")
        return value

    @model_validator(mode="after")
    def _sourced(self) -> Figure:
        if self.currency is not None and not _CODE_RE.fullmatch(self.currency):
            raise ValueError("currency deve ser código ISO (ex.: USD)")
        if self.value is None:
            return self
        if not self.source_url or self.checked_at is None:
            raise ValueError("value exige source_url e checked_at")
        return self


class Percentage(Figure):
    @model_validator(mode="after")
    def _fraction(self) -> Percentage:
        if self.value is not None:
            out = Decimal(self.value)
            if not Decimal(0) <= out < Decimal(1):
                raise ValueError("percentual deve estar entre 0 e 1 (ex.: \"0.035\" = 3,5 %)")
        return self


class FixedFee(Figure):
    @model_validator(mode="after")
    def _money(self) -> FixedFee:
        if self.value is not None:
            if Decimal(self.value) < 0:
                raise ValueError("taxa fixa não pode ser negativa")
            if self.currency is None:
                raise ValueError("taxa fixa exige currency")
        return self


class FxCost(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    spread_pct: Percentage = Field(default_factory=Percentage)
    iof_pct: Percentage = Field(default_factory=Percentage)
    fee_pct: Percentage = Field(default_factory=Percentage)
    fee_fixed: FixedFee = Field(default_factory=FixedFee)


class Institution(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    name: str = Field(min_length=2)
    country: Country
    kind: Kind
    status: Status = "active"
    discontinued_note: str | None = None
    currencies_held: tuple[str, ...] | None = None
    opens_remotely: bool | None = None
    requires: str | None = None
    api: Api | None = None
    api_source_url: str | None = None
    source_url: str | None = None
    checked_at: date | None = None
    fx_cost: FxCost = Field(default_factory=FxCost)

    @field_validator("id")
    @classmethod
    def _id(cls, value: str) -> str:
        if not _ID_RE.fullmatch(value):
            raise ValueError("id deve ser minúsculo, sem espaços (ex.: itau-py-cuenta-full)")
        return value

    @field_validator("currencies_held")
    @classmethod
    def _codes(cls, value: tuple[str, ...] | None) -> tuple[str, ...] | None:
        if value is None:
            return None
        for code in value:
            if not _CODE_RE.fullmatch(code):
                raise ValueError(f"moeda inválida: {code!r}")
        if len(set(value)) != len(value):
            raise ValueError("currencies_held repete moeda")
        return value

    @model_validator(mode="after")
    def _checks(self) -> Institution:
        facts = (self.currencies_held, self.opens_remotely, self.requires)
        if any(f is not None for f in facts) and (not self.source_url or self.checked_at is None):
            raise ValueError("fatos não nulos exigem source_url e checked_at da entrada")
        if self.api is not None and (not self.api_source_url or self.checked_at is None):
            raise ValueError("api exige api_source_url e checked_at")
        if self.status == "discontinued" and not self.discontinued_note:
            raise ValueError("discontinued exige discontinued_note")
        if self.status == "active" and self.discontinued_note:
            raise ValueError("discontinued_note só existe com status discontinued")
        return self


def _load_rows(text: str) -> list[tuple[str, dict[str, Any]]]:
    raw = json.loads(text)
    if not isinstance(raw, list):
        raise ValueError("institutions: o arquivo deve ser uma lista JSON")
    rows: list[tuple[str, dict[str, Any]]] = []
    seen: set[str] = set()
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ValueError(f"institutions[{index}]: cada linha deve ser um objeto JSON")
        line_id = str(entry.get("id", f"#{index}"))
        if line_id in seen:
            raise ValueError(f"institutions[{line_id}]: id duplicado")
        seen.add(line_id)
        rows.append((line_id, entry))
    return rows


def _first_error(exc: ValidationError) -> str:
    err = exc.errors()[0]
    msg = str(err.get("msg", "inválido")).removeprefix("Value error, ")
    loc = ".".join(str(part) for part in err.get("loc", ()))
    return f"{loc}: {msg}" if loc and not msg.startswith(loc) else msg


def parse_institutions(text: str) -> dict[str, Institution]:
    out: dict[str, Institution] = {}
    for line_id, entry in _load_rows(text):
        try:
            out[line_id] = Institution.model_validate(entry)
        except ValidationError as exc:
            raise ValueError(f"institutions[{line_id}]: {_first_error(exc)}") from exc
    return out


@lru_cache(maxsize=1)
def load_institutions() -> dict[str, Institution]:
    """Cadastro de `data/institutions.json`; lido uma vez por processo."""
    text = resources.files("fronteira_fx").joinpath("data/institutions.json").read_text("utf-8")
    return parse_institutions(text)
