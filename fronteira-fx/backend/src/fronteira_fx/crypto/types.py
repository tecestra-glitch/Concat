"""Tipos imutáveis de cripto. Preço e quantidade sempre em `Decimal`; datas em UTC."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

Side = Literal["buy", "sell"]


def utc_now() -> datetime:
    return datetime.now(tz=UTC)


@dataclass(frozen=True, slots=True)
class Level:
    price: Decimal
    qty: Decimal


@dataclass(frozen=True, slots=True)
class OrderBook:
    """Livro de ofertas somente leitura. `bids` do maior para o menor preço, `asks` do menor para o maior."""

    venue: str
    symbol: str
    bids: tuple[Level, ...]
    asks: tuple[Level, ...]
    fetched_at: datetime = field(default_factory=utc_now)
    executable: bool = False  # leitura: este módulo nunca executa nada


@dataclass(frozen=True, slots=True)
class Ticker:
    venue: str
    symbol: str
    last: Decimal | None
    bid: Decimal | None
    ask: Decimal | None
    fetched_at: datetime = field(default_factory=utc_now)
    executable: bool = False


@dataclass(frozen=True, slots=True)
class VenueFee:
    """Taxa por lado, como fração (0,001 = 0,10%). `None` = não confirmada pela fonte: nunca assumir zero."""

    venue: str
    maker: Decimal | None
    taker: Decimal | None
    source: str


@dataclass(frozen=True, slots=True)
class VwapFill:
    """Preço médio ponderado para um tamanho alvo, antes e depois da taxa taker da exchange."""

    venue: str
    symbol: str
    side: Side
    target_qty: Decimal
    filled_qty: Decimal
    vwap: Decimal | None  # None quando não há profundidade
    net_price: Decimal | None  # compra: vwap * (1 + taker); venda: vwap * (1 - taker)
    fee: VenueFee
    complete: bool  # True se o livro cobriu o tamanho alvo inteiro
    fetched_at: datetime
    executable: bool = False
