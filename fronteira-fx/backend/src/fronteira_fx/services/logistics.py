"""Dados versionados do motor de arbitragem: deslocamento entre cidades (`data/transport.json`) e trilhos de
transferência entre contas e lugares (`data/rails.json`).

Padrão igual ao de `market_hours`: arquivo empacotado, pydantic, `lru_cache`, e qualquer violação vira `ValueError`
com o id da linha. Valor `null` significa custo desconhecido: quem consome transforma isso em `confidence: incomplete`,
nunca em zero. Dinheiro entra como string decimal; número JSON é recusado para não passar por ponto flutuante.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from importlib import resources
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

Currency = Literal["BRL", "PYG", "USD"]
City = Literal["CDE", "ASU", "PJC", "ENC", "FOZ", "PPO"]
TransportMode = Literal["bus", "car", "taxi", "walk", "flight"]
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,63}$")
_ENDPOINT_RE = re.compile(r"^[a-z][a-z_]{1,31}$")


def _decimal_string(value: Any, field: str) -> Decimal:
    if not isinstance(value, str):
        raise ValueError(f"{field} deve ser string decimal (ex.: \"35.50\"), não número JSON")
    try:
        out = Decimal(value)
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} não é um decimal válido: {value!r}") from None
    if not out.is_finite():
        raise ValueError(f"{field} deve ser finito")
    return out


class Money(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    amount: Decimal
    currency: Currency

    @field_validator("amount", mode="before")
    @classmethod
    def _amount(cls, value: Any) -> Decimal:
        out = _decimal_string(value, "amount")
        if out < 0:
            raise ValueError("amount não pode ser negativo")
        return out


class TransportRoute(BaseModel):
    """Rota entre duas cidades. `cost` null = custo não validado (o motor marca `incomplete`)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    from_city: City
    to_city: City
    mode: TransportMode
    cost: Money | None = None
    minutes: int = Field(ge=0, le=60 * 72)
    border: bool
    symmetric: bool
    source_url: str | None = None
    checked_at: str | None = None
    verified: bool

    @field_validator("id")
    @classmethod
    def _id(cls, value: str) -> str:
        if not _ID_RE.match(value):
            raise ValueError("id deve ser minúsculo, sem espaços (ex.: cde-asu)")
        return value

    @model_validator(mode="after")
    def _verified_needs_source(self) -> TransportRoute:
        if self.from_city == self.to_city:
            raise ValueError("from_city e to_city devem ser diferentes")
        if self.verified and (not self.source_url or not self.checked_at):
            raise ValueError("verified exige source_url e checked_at")
        return self


class Rail(BaseModel):
    """Trilho de transferência: de um lugar/instituição para outro, com custos. `to_currency` ausente = mesma moeda."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    id: str
    from_: str = Field(alias="from")
    to: str
    currency: Currency
    to_currency: Currency | None = None
    fee_fixed: Money | None = None
    fee_pct: Decimal | None = None
    iof_pct: Decimal | None = None
    minutes: int = Field(ge=0, le=60 * 24 * 30)
    min_amount: Decimal | None = None
    max_amount: Decimal | None = None
    source_url: str | None = None
    checked_at: str | None = None
    verified: bool

    @field_validator("id")
    @classmethod
    def _id(cls, value: str) -> str:
        if not _ID_RE.match(value):
            raise ValueError("id deve ser minúsculo, sem espaços (ex.: pix-br-bank-revolut-brl)")
        return value

    @field_validator("from_", "to")
    @classmethod
    def _endpoint(cls, value: str) -> str:
        if not _ENDPOINT_RE.match(value):
            raise ValueError("endpoint deve ser minúsculo com _ (ex.: br_bank, py_bank, cash)")
        return value

    @field_validator("fee_pct", "iof_pct", mode="before")
    @classmethod
    def _rate(cls, value: Any) -> Any:
        if value is None:
            return None
        out = _decimal_string(value, "percentual")
        if not Decimal(0) <= out < Decimal(1):
            raise ValueError("percentual deve estar entre 0 e 1 (ex.: \"0.0035\" = 0,35 %)")
        return out

    @field_validator("min_amount", "max_amount", mode="before")
    @classmethod
    def _bound(cls, value: Any) -> Any:
        if value is None:
            return None
        out = _decimal_string(value, "limite")
        if out < 0:
            raise ValueError("limite não pode ser negativo")
        return out

    @model_validator(mode="after")
    def _checks(self) -> Rail:
        if self.verified and (not self.source_url or not self.checked_at):
            raise ValueError("verified exige source_url e checked_at")
        if self.from_ == self.to and (self.to_currency or self.currency) == self.currency:
            raise ValueError("trilho de um lugar para ele mesmo na mesma moeda não faz sentido")
        if self.min_amount is not None and self.max_amount is not None and self.min_amount > self.max_amount:
            raise ValueError("min_amount maior que max_amount")
        return self

    @property
    def out_currency(self) -> str:
        return self.to_currency or self.currency

    @property
    def converts(self) -> bool:
        return self.out_currency != self.currency


def _load_rows(text: str, name: str) -> list[tuple[str, dict[str, Any]]]:
    raw = json.loads(text)
    if not isinstance(raw, list):
        raise ValueError(f"{name}: o arquivo deve ser uma lista JSON")
    rows: list[tuple[str, dict[str, Any]]] = []
    seen: set[str] = set()
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ValueError(f"{name}[{index}]: cada linha deve ser um objeto JSON")
        line_id = str(entry.get("id", f"#{index}"))
        if line_id in seen:
            raise ValueError(f"{name}[{line_id}]: id duplicado")
        seen.add(line_id)
        rows.append((line_id, entry))
    return rows


def parse_transport(text: str) -> dict[str, TransportRoute]:
    routes: dict[str, TransportRoute] = {}
    for line_id, entry in _load_rows(text, "transport"):
        try:
            routes[line_id] = TransportRoute.model_validate(entry)
        except ValidationError as exc:
            raise ValueError(f"transport[{line_id}]: {_first_error(exc)}") from exc
    return routes


def parse_rails(text: str) -> dict[str, Rail]:
    rails: dict[str, Rail] = {}
    for line_id, entry in _load_rows(text, "rails"):
        try:
            rails[line_id] = Rail.model_validate(entry)
        except ValidationError as exc:
            raise ValueError(f"rails[{line_id}]: {_first_error(exc)}") from exc
    return rails


def _first_error(exc: ValidationError) -> str:
    err = exc.errors()[0]
    msg = str(err.get("msg", "inválido"))
    msg = msg.removeprefix("Value error, ")
    loc = ".".join(str(part) for part in err.get("loc", ()))
    return f"{loc}: {msg}" if loc and not msg.startswith(loc) else msg


def _read(name: str) -> str:
    return resources.files("fronteira_fx").joinpath(f"data/{name}").read_text("utf-8")


@lru_cache(maxsize=1)
def load_transport() -> dict[str, TransportRoute]:
    """Rotas entre cidades de `data/transport.json`; lido uma vez por processo."""
    return parse_transport(_read("transport.json"))


@lru_cache(maxsize=1)
def load_rails() -> dict[str, Rail]:
    """Trilhos de `data/rails.json`; lido uma vez por processo."""
    return parse_rails(_read("rails.json"))


def find_rail(rails: dict[str, Rail] | list[Rail], src: str, dst: str, currency: str) -> Rail | None:
    """Trilho de `src` para `dst` que sai na moeda `currency` (o primeiro na ordem do arquivo)."""
    values = rails.values() if isinstance(rails, dict) else rails
    for rail in values:
        if rail.from_ == src and rail.to == dst and rail.currency == currency:
            return rail
    return None
