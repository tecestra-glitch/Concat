"""Shared adapter contract. Every provider adapter implements `Adapter`.

An adapter turns a provider's website/API into normalised `QuoteDraft`s plus an
`EvidenceDraft` (what was fetched, when, hash, excerpt) so the result can be
audited later. Adapters never touch the database: the collector service does.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal, Protocol

Currency = Literal["BRL", "USD", "PYG"]
City = Literal["CDE", "ASU", "PJC"] | None
# "reference" marks third-party aggregator quotes (e.g. dolarPy): never executable, never a counter price.
Modality = Literal["cash", "transfer", "account", "card_debit", "card_credit", "card_virtual", "reference"]
QuoteKind = Literal["market_reference", "indicative", "executable"]
# "aggregator" is the channel of a third-party aggregator: neither a counter nor an app you can transact in.
Channel = Literal["digital", "physical", "aggregator"]


# How the adapter obtains its data (shown as a seal on the Fontes screen and in list_sources):
#   api_oficial      documented public API of the provider or of its official source (e.g. BCP reference table)
#   endpoint_interno undocumented JSON that the site's own front end calls; replayed with plain HTTP
#   html             server-rendered page parsed with selectolax (no JS needed)
#   navegador        needs a headless browser (Playwright) to reach the price
Integration = Literal["api_oficial", "endpoint_interno", "html", "navegador"]


class AdapterStatus(StrEnum):
    OK = "ok"
    DEGRADED = "degraded"      # partial data, layout drift, some branches missing
    BLOCKED = "blocked"        # 403/captcha/anti-bot
    STALE = "stale"            # page served but declared timestamp is old
    NEEDS_SESSION = "needs_session"  # login required -> account-connection phase
    ERROR = "error"


@dataclass(slots=True)
class Fee:
    label: str
    amount: Decimal
    currency: Currency


@dataclass(slots=True)
class QuoteDraft:
    source_id: str
    base: Currency
    quote: Currency
    buy: Decimal | None
    sell: Decimal | None
    unit_note: str                       # e.g. "PYG por 1 USD"
    modality: Modality
    kind: QuoteKind
    channel: Channel
    city: City = None
    branch_id: str | None = None
    amount_base: Decimal | None = None   # when the quote depends on the amount typed
    context: dict[str, Any] | None = None  # payment/receive/bank/promo etc. NEVER mix contexts
    fees: list[Fee] = field(default_factory=list)
    declared_updated_at: datetime | None = None
    valid_until: datetime | None = None


@dataclass(slots=True)
class EvidenceDraft:
    source_id: str
    kind: Literal["html", "json", "screenshot", "manual"]
    url: str
    captured_at: datetime
    sha256: str
    excerpt: str                      # short, human-readable proof (<= 2000 chars)
    rules: list[str]                  # parser rules/version used
    raw_path: str | None = None       # optional path to stored raw payload


@dataclass(slots=True)
class AdapterResult:
    status: AdapterStatus
    quotes: list[QuoteDraft]
    evidence: EvidenceDraft | None
    message: str | None = None        # explicit reason when not OK


@dataclass(slots=True)
class AdapterInfo:
    id: str
    name: str
    kind: Literal["exchange_house", "remittance", "bank", "fintech", "central_bank"]
    method: Literal["official_api", "html", "browser", "manual"]
    url: str
    capabilities: list[str]
    limitations: list[str]
    cities: list[str]
    currencies: list[str]
    poll_interval_s: int = 300
    allowed_domains: list[str] = field(default_factory=list)  # navigation restricted to these
    integration: Integration = "html"


class Adapter(Protocol):
    info: AdapterInfo

    async def fetch(self, **params: Any) -> AdapterResult:
        """Fetch live data. Must be idempotent and never raise for provider-side
        failures: return AdapterResult(status=..., message=...) instead."""
        ...

    def parse(self, raw: str | bytes, *, captured_at: datetime, url: str, **params: Any) -> AdapterResult:
        """Pure function: raw payload -> result. Used by tests with fixtures."""
        ...
