"""Pydantic v2 schemas mirroring docs/api-contract.md. Decimals are serialised as strings."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, field_validator, model_validator

from .decimal_utils import fmt

DecStr = Annotated[Decimal, PlainSerializer(lambda v: fmt(v), return_type=str, when_used="json-unless-none")]

Currency = Literal["BRL", "USD", "PYG"]
City = Literal["CDE", "ASU", "PJC"]
Channel = Literal["digital", "physical", "aggregator"]
Modality = Literal["cash", "transfer", "account", "card_debit", "card_credit", "card_virtual", "reference"]
QuoteKind = Literal["market_reference", "indicative", "executable"]
SourceMethod = Literal["official_api", "html", "browser", "manual"]
SourceKind = Literal["exchange_house", "remittance", "bank", "fintech", "central_bank"]
Health = Literal["ok", "degraded", "blocked", "stale", "unknown"]
Confidence = Literal["quoted", "estimated", "incomplete"]
DataMode = Literal["real", "simulation", "demo"]
OpportunityKind = Literal["cycle", "remittance_saving", "purchase_saving"]
AccountKind = Literal["bank", "fintech", "cash", "card_debit", "card_credit", "card_virtual"]
Location = Literal["ASU", "CDE", "PJC", "digital"]
Objective = Literal["cycle", "remittance", "purchase"]
Window = Literal["1h", "24h"]


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class FeeOut(ApiModel):
    label: str
    amount: DecStr | None = None
    currency: str
    pct: DecStr | None = None  # share of the input amount (e.g. "0.015"); omitted when the fee is fixed only


class Coverage(ApiModel):
    cities: list[str] = Field(default_factory=list)
    currencies: list[str] = Field(default_factory=list)


class SourceOut(ApiModel):
    id: str
    name: str
    kind: str
    method: str
    url: str
    health: str
    last_success_at: datetime | None = None
    last_error: str | None = None
    capabilities: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    coverage: Coverage = Field(default_factory=Coverage)
    poll_interval_s: int = 300
    data_mode: str = "real"

    @classmethod
    def from_row(cls, row: Any) -> SourceOut:
        return cls(
            id=row.id,
            name=row.name,
            kind=row.kind,
            method=row.method,
            url=row.url or "",
            health=row.health,
            last_success_at=row.last_success_at,
            last_error=row.last_error,
            capabilities=list(row.capabilities or []),
            limitations=list(row.limitations or []),
            coverage=Coverage(cities=list(row.coverage_cities or []), currencies=list(row.coverage_currencies or [])),
            poll_interval_s=row.poll_interval_s,
            data_mode=row.data_mode,
        )


class BranchOut(ApiModel):
    id: str
    source_id: str
    name: str
    city: str | None = None
    address: str | None = None


class QuoteOut(ApiModel):
    id: str
    source_id: str
    branch_id: str | None = None
    city: str | None = None
    base: str
    quote: str
    buy: DecStr | None = None
    sell: DecStr | None = None
    unit_note: str = ""
    amount_base: DecStr | None = None
    modality: str
    kind: str
    channel: str
    context: dict[str, Any] | None = None
    fees: list[FeeOut] = Field(default_factory=list)
    captured_at: datetime
    declared_updated_at: datetime | None = None
    valid_until: datetime | None = None
    evidence_id: str | None = None
    data_mode: str = "real"
    series_key: str = Field(description="chave comparável da série (D2), aceita em GET /v1/history?key=")


class HistoryPoint(ApiModel):
    t: datetime
    buy: DecStr | None = None
    sell: DecStr | None = None
    mid: DecStr | None = None


class HistorySeries(ApiModel):
    key: str
    points: list[HistoryPoint] = Field(default_factory=list)


class VolatilityOut(ApiModel):
    key: str
    window: str
    grid_s: int
    returns_used: int
    min_returns: int
    stdev_pct_per_5m: DecStr | None = None
    coverage_pct: DecStr
    gaps: int
    status: Literal["ok", "insufficient_data", "stale_input"]
    unit: str = "% por intervalo de 5 min"


class AccountOut(ApiModel):
    id: str
    institution: str
    label: str
    currency: str
    kind: str
    location: str
    balance_free: DecStr
    balance_reserved: DecStr
    balance_in_transit: DecStr
    updated_at: datetime
    data_mode: str = "real"


class AccountCreate(ApiModel):
    institution: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=200)
    currency: Currency
    kind: AccountKind = "bank"
    location: Location = "digital"
    balance_free: Decimal = Decimal(0)
    balance_reserved: Decimal = Decimal(0)
    balance_in_transit: Decimal = Decimal(0)


class AccountPatch(ApiModel):
    label: str | None = Field(default=None, max_length=200)
    location: Location | None = None
    balance_free: Decimal | None = None
    balance_reserved: Decimal | None = None
    balance_in_transit: Decimal | None = None


class PositionIn(ApiModel):
    currency: Currency
    account_id: str | None = None
    institution: str | None = None
    location: str = "digital"
    modality: Modality = "account"
    amount: Decimal | None = None


class PositionOut(ApiModel):
    currency: str
    account_id: str | None = None
    institution: str | None = None
    location: str
    modality: str
    amount: DecStr | None = None


class RouteStepOut(ApiModel):
    n: int
    description: str
    from_: PositionOut = Field(alias="from", serialization_alias="from")
    to: PositionOut
    rate: DecStr | None = None
    rate_note: str = ""
    amount_in: DecStr
    amount_out: DecStr
    fees: list[FeeOut] = Field(default_factory=list)
    duration: str = ""
    promo: str | None = None
    confidence: Confidence
    evidence_id: str | None = None


class OpportunityOut(ApiModel):
    id: str
    title: str
    kind: str
    channel: str
    city: str | None = None
    capital_brl: DecStr
    final_value_brl: DecStr
    net_gain_brl: DecStr
    roi: DecStr
    effective_rate: DecStr | None = None
    valuation_currency: str = "BRL"
    steps: list[RouteStepOut] = Field(default_factory=list)
    confidence: Confidence
    pending_costs: list[str] = Field(default_factory=list)
    in_main_ranking: bool
    ranking_reason: str = ""
    comparable_best_digital_roi: DecStr | None = None
    computed_at: datetime
    data_mode: str = "real"


class EvidenceOut(ApiModel):
    id: str
    source_id: str
    kind: str
    url: str
    captured_at: datetime
    sha256: str
    excerpt: str
    rules: list[str] = Field(default_factory=list)
    data_mode: str = "real"


class JournalEntryOut(ApiModel):
    id: str
    ts: datetime
    kind: str
    text: str
    amounts: list[FeeOut] = Field(default_factory=list)
    account_ids: list[str] = Field(default_factory=list)
    data_mode: str = "real"


class JournalEntryCreate(ApiModel):
    kind: Literal["note", "operation", "reconciliation"] = "note"
    text: str = Field(min_length=1)
    amounts: list[FeeOut] = Field(default_factory=list)
    account_ids: list[str] = Field(default_factory=list)
    ts: datetime | None = None


class StreamEventOut(ApiModel):
    id: str
    type: str
    ts: datetime
    payload: dict[str, Any] = Field(default_factory=dict)


class HealthOut(ApiModel):
    status: str
    data_mode: str
    db: str
    version: str
    server_time: datetime


class SnapshotOut(ApiModel):
    cursor: str
    quotes: list[QuoteOut]
    sources: list[SourceOut]
    opportunities: list[OpportunityOut]
    server_time: datetime
    data_mode: str


class QuoteRequestIn(ApiModel):
    source_id: str
    params: dict[str, Any] = Field(default_factory=dict)


class QuoteRequestOut(ApiModel):
    status: Literal["done", "queued", "blocked"]
    quote: QuoteOut | None = None
    job_id: str | None = None
    reason: str | None = None


class SimulationRequest(ApiModel):
    capital_brl: Decimal = Field(gt=0)
    objective: Objective = "cycle"
    destination: PositionIn | None = None
    valuation_currency: Currency = "BRL"
    channels: list[Channel] = Field(default_factory=lambda: ["digital", "physical"])
    amounts: list[Decimal] | None = None
    persist: bool = False


class BoundaryOut(ApiModel):
    low: DecStr
    high: DecStr
    low_winner: str | None = None
    high_winner: str | None = None
    low_roi_sign: str
    high_roi_sign: str
    reason: str
    refined: bool


class SearchOut(ApiModel):
    amounts_tested: list[DecStr] = Field(default_factory=list)
    boundaries: list[BoundaryOut] = Field(default_factory=list)


class SimulationResponse(ApiModel):
    opportunities: list[OpportunityOut]
    search: SearchOut
    simulation_id: str | None = None


class FeeIn(ApiModel):
    label: str
    amount: Decimal | None = None
    currency: str
    rate_to_output: Decimal | None = None


class StepSpecIn(ApiModel):
    description: str
    from_: PositionIn = Field(alias="from")
    to: PositionIn
    rate: Decimal | None = None
    rate_note: str = ""
    fees: list[FeeIn] = Field(default_factory=list)
    duration: str = ""
    promo: str | None = None
    confidence: Confidence = "quoted"
    evidence_id: str | None = None


class CycleSimulationRequest(ApiModel):
    capital: Decimal = Field(gt=0)
    steps: list[StepSpecIn] = Field(min_length=1)
    valuation_currency: Currency = "BRL"
    valuation_rates: dict[str, Decimal] = Field(default_factory=dict)


class RouteResultOut(ApiModel):
    steps: list[RouteStepOut]
    start_currency: str
    final_currency: str
    valuation_currency: str
    total_debit: DecStr
    net_credit: DecStr
    total_capital_allocated: DecStr | None = None
    final_available: DecStr | None = None
    effective_rate: DecStr | None = None
    cycle_profit: DecStr | None = None
    roi: DecStr | None = None
    total_fees_valued: DecStr | None = None
    confidence: Confidence
    pending_costs: list[str] = Field(default_factory=list)


# ---- position graph / cycles (D1: snake_case, money as decimal strings) -------------------------

EdgeKind = Literal["quote", "transfer", "deposit", "withdraw", "travel"]
LegKind = Literal["exchange", "transfer", "travel", "deposit", "withdraw"]
# presencial: casa, dinheiro vivo, deslocamento; assistida: o usuário faz pelo app do banco; automatizavel: nenhuma hoje
ChannelKind = Literal["presencial", "assistida", "automatizavel"]


class EdgeOut(ApiModel):
    from_: str = Field(alias="from", serialization_alias="from")
    to: str
    kind: EdgeKind
    rate: DecStr
    fee_pct: DecStr = Decimal(0)
    fee_fixed: DecStr = Decimal(0)
    minutes: int = 0
    via: str
    confidence: Confidence
    evidence_id: str | None = None
    channel: ChannelKind = "presencial"


class LegCostsOut(ApiModel):
    """Custos de uma perna, na moeda em que foram pagos (`currency`). `spread` null = sem taxa de referência."""

    currency: Currency
    spread: DecStr | None = None
    fees: DecStr
    iof: DecStr
    transport: DecStr


class LegOut(ApiModel):
    kind: LegKind
    channel: ChannelKind
    from_: str = Field(alias="from", serialization_alias="from")
    to: str
    via: str
    minutes: int
    border: bool = False
    amount_in: DecStr
    amount_out: DecStr
    costs: LegCostsOut


class CycleOut(ApiModel):
    start: str
    path: list[str]
    edges: list[EdgeOut]
    legs: list[LegOut] = []
    amount_in: DecStr
    amount_out: DecStr
    gain: DecStr
    roi: DecStr
    # ganho líquido em BRL, USD e PYG (null quando falta taxa de valoração); custos na moeda de partida
    gain_by_currency: dict[Currency, DecStr | None] | None = None
    costs: dict[Literal["spread", "fees", "iof", "transport"], DecStr | None] | None = None
    requires_declaration: bool = False
    minutes: int
    confidence: Confidence
    data_mode: DataMode


# ---- watch ---------------------------------------------------------------------------------------

WatchStatusValue = Literal["ok", "degraded", "blocked", "stale", "error", "needs_session"]
ChangeKind = Literal["quote_change", "layout_change", "status_change"]


class WatchStatusOut(ApiModel):
    source_id: str
    enabled: bool
    interval_s: int
    min_interval_s: int
    max_interval_s: int
    next_run_at: datetime | None = None
    last_run_at: datetime | None = None
    last_change_at: datetime | None = None
    changes_24h: int = 0
    errors_in_row: int = 0
    etag: str | None = None
    last_modified: str | None = None
    content_hash: str | None = None
    status: str


class WatchPatch(ApiModel):
    interval_s: int | None = Field(default=None, ge=10, le=86400)
    enabled: bool | None = None
    min_interval_s: int | None = Field(default=None, ge=10)
    max_interval_s: int | None = Field(default=None, ge=10)


class ChangeOut(ApiModel):
    id: str
    source_id: str
    ts: datetime
    kind: str
    summary: str
    before: dict[str, Any] = Field(default_factory=dict)
    after: dict[str, Any] = Field(default_factory=dict)
    evidence_id: str | None = None


# ---- alerts --------------------------------------------------------------------------------------

AlertKind = Literal["cycle_roi", "quote_move", "source_down", "opportunity_new", "cycle_net_gain"]
AlertChannel = Literal["ui", "telegram", "webhook", "email"]


class AlertRuleOut(ApiModel):
    id: str
    name: str
    kind: str
    threshold: DecStr | None = None
    params: dict[str, Any] | None = None
    channel: str
    target: str | None = None
    cooldown_s: int
    enabled: bool
    last_fired_at: datetime | None = None


class AlertRuleCreate(ApiModel):
    name: str = Field(min_length=1, max_length=200)
    kind: AlertKind
    threshold: Decimal | None = None
    params: dict[str, Any] | None = None
    channel: AlertChannel = "ui"
    target: str | None = None
    cooldown_s: int = Field(default=600, ge=0)
    enabled: bool = True

    @model_validator(mode="after")
    def _check_net_gain(self) -> AlertRuleCreate:
        # cycle_net_gain: threshold é o ganho líquido mínimo, na moeda de params.currency
        if self.kind != "cycle_net_gain":
            return self
        currency = (self.params or {}).get("currency")
        if currency not in ("BRL", "USD", "PYG"):
            raise ValueError("cycle_net_gain exige params.currency: BRL, USD ou PYG")
        if self.threshold is None or self.threshold < 0:
            raise ValueError("cycle_net_gain exige threshold (ganho líquido mínimo) maior ou igual a zero")
        return self


class AlertRulePatch(ApiModel):
    name: str | None = Field(default=None, max_length=200)
    threshold: Decimal | None = None
    params: dict[str, Any] | None = None
    channel: AlertChannel | None = None
    target: str | None = None
    cooldown_s: int | None = Field(default=None, ge=0)
    enabled: bool | None = None


class AlertEventOut(ApiModel):
    id: str
    rule_id: str
    ts: datetime
    message: str
    payload: dict[str, Any] = Field(default_factory=dict)
    channel: str
    delivered: bool
    error: str | None = None


# ---- rag -----------------------------------------------------------------------------------------


class RagDocumentCreate(ApiModel):
    title: str = Field(min_length=1, max_length=300)
    text: str = Field(min_length=1)
    source: str | None = None
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] | None = None


class RagDocumentCreated(ApiModel):
    id: str
    chunks: int


class RagDocumentOut(ApiModel):
    id: str
    title: str | None = None
    source: str | None = None
    tags: list[str] = Field(default_factory=list)
    chunks: int
    created_at: datetime


class RagHit(ApiModel):
    id: str
    document_id: str
    title: str | None = None
    snippet: str
    score: float
    source: str | None = None
    tags: list[str] = Field(default_factory=list)


# ---- memory --------------------------------------------------------------------------------------

MemoryKind = Literal["preference", "decision", "fact", "outcome"]


class MemoryCreate(ApiModel):
    kind: MemoryKind
    text: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)
    ttl_days: int | None = Field(default=None, ge=1)
    source: Literal["user", "agent"] = "user"


class MemoryOut(ApiModel):
    id: str
    kind: str
    text: str
    tags: list[str] = Field(default_factory=list)
    created_at: datetime
    expires_at: datetime | None = None
    source: str


class MemorySummary(ApiModel):
    """One line per kind (`Preferências`, `Decisões`, `Fatos`, `Resultados`), newest first; `""` when empty."""

    summary: str


# ---- planos de execução (fase A: sem execução) -----------------------------------------------------

PlanStatus = Literal["proposed", "approved", "in_progress", "done", "rejected", "expired"]
StepStatus = Literal["pending", "done"]


class PlanCreateIn(ApiModel):
    """Plano a partir de um ciclo: o `start` e o `path` (nós, o último igual ao primeiro) de `/opportunities/cycles`."""

    start: str = Field(min_length=1, max_length=120)
    path: list[str] = Field(min_length=2, max_length=7)


class StepDoneIn(ApiModel):
    """Passo concluído: valor realizado (string decimal, na moeda de saída do passo) e nota opcional."""

    actual_out: str = Field(min_length=1, max_length=40)
    note: str | None = Field(default=None, max_length=500)

    @field_validator("actual_out")
    @classmethod
    def _decimal(cls, value: str) -> str:
        try:
            out = Decimal(value)
        except (InvalidOperation, ValueError):
            raise ValueError("actual_out deve ser uma string decimal") from None
        if not out.is_finite() or out < 0:
            raise ValueError("actual_out deve ser finito e não negativo")
        return value


class PlanStepOut(ApiModel):
    n: int
    kind: LegKind
    channel: ChannelKind
    text: str
    from_: str = Field(alias="from", serialization_alias="from")
    to: str
    amount_in: DecStr
    amount_out_expected: DecStr
    minutes: int
    status: StepStatus
    actual_out: DecStr | None = None
    note: str | None = None
    done_at: datetime | None = None


class PlanOut(ApiModel):
    id: str
    status: PlanStatus
    start: str
    path: list[str]
    currency: Currency
    amount_in: DecStr
    amount_out_expected: DecStr
    gain_expected: DecStr
    gain_by_currency: dict[Currency, DecStr | None] | None = None
    confidence: Confidence
    minutes: int
    requires_declaration: bool = False
    quotes_as_of: datetime
    quote_max_age_s: int
    created_at: datetime
    decided_at: datetime | None = None
    completed_at: datetime | None = None
    data_mode: DataMode
    steps: list[PlanStepOut] = []
