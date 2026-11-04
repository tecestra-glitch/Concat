"""Contratos das rotas /v1/connections. Segredos entram como SecretStr (não aparecem em repr) e nunca saem."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from ..schemas import Currency, DecStr
from .statement import ALLOWED_DATE_FORMATS

ConnectionKind = Literal["consent", "readonly_key", "statement", "manual"]
ConnectionStatus = Literal["pending", "active", "error"]
StatementFormat = Literal["csv", "ofx"]


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class BalanceOut(ApiModel):
    asset: str
    free: DecStr
    locked: DecStr


class ConnectionCreate(ApiModel):
    institution: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    label: str = Field(min_length=1, max_length=200)
    kind: ConnectionKind
    account_id: str | None = Field(default=None, max_length=36)
    api_key: SecretStr | None = None  # só readonly_key
    api_secret: SecretStr | None = None  # só readonly_key


class KeyValidationIn(ApiModel):
    institution: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    api_key: SecretStr
    api_secret: SecretStr


class KeyCheckOut(ApiModel):
    ok: bool
    institution: str
    flags: dict[str, bool | None]
    reasons: list[str]
    balances: list[BalanceOut]


class ConnectionOut(ApiModel):
    id: str
    institution: str
    label: str
    kind: ConnectionKind
    status: ConnectionStatus
    data_mode: str
    account_id: str | None = None
    key_hint: str | None = None  # só os 4 últimos caracteres da chave pública
    balances: list[BalanceOut] | None = None
    last_error: str | None = None
    last_synced_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class CsvMappingIn(ApiModel):
    date: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1, max_length=64)
    amount: str = Field(min_length=1, max_length=64)
    currency: str | None = Field(default=None, max_length=64)
    date_format: str = "%Y-%m-%d"
    delimiter: Literal[",", ";", "\t"] = ","

    @field_validator("date_format")
    @classmethod
    def _allowed_format(cls, value: str) -> str:
        if value not in ALLOWED_DATE_FORMATS:
            raise ValueError("date_format não permitido")
        return value


class StatementImportIn(ApiModel):
    format: StatementFormat
    content: str = Field(min_length=1, max_length=512 * 1024)
    mapping: CsvMappingIn | None = None  # obrigatório para csv
    default_currency: Currency | None = None


class StatementImportOut(ApiModel):
    connection_id: str
    format: StatementFormat
    imported: int
    duplicates: int
    account_id: str | None = None
    balance_delta: DecStr = Decimal(0)
    account_balance_free: DecStr | None = None


class OpenFinanceConsentIn(ApiModel):
    institution: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
