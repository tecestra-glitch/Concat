"""VWAP de um tamanho alvo sobre um livro de ofertas. Puro, sem rede, em `Decimal`."""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal

from .types import Level, OrderBook, Side, VenueFee, VwapFill

ZERO = Decimal(0)
ONE = Decimal(1)


def _walk(levels: Iterable[Level], target: Decimal) -> tuple[Decimal, Decimal]:
    """Consome níveis até `target`. Retorna (quantidade preenchida, custo total na moeda cotada)."""
    remaining = target
    filled = ZERO
    cost = ZERO
    for level in levels:
        if remaining <= ZERO:
            break
        if level.qty <= ZERO or level.price <= ZERO:
            continue
        take = min(remaining, level.qty)
        filled += take
        cost += take * level.price
        remaining -= take
    return filled, cost


def vwap_for_target(book: OrderBook, side: Side, target: Decimal, fee: VenueFee) -> VwapFill:
    """VWAP para comprar (consome asks, do menor preço) ou vender (consome bids, do maior preço).

    Se o livro não cobrir `target`, retorna `complete=False` com o VWAP do que foi possível preencher.
    Nunca arredonda: a exibição é que arredonda.
    """
    if target <= ZERO:
        raise ValueError("target must be positive")
    if side == "buy":
        levels = sorted(book.asks, key=lambda lvl: lvl.price)
    elif side == "sell":
        levels = sorted(book.bids, key=lambda lvl: lvl.price, reverse=True)
    else:  # pragma: no cover - guarded by the Literal type
        raise ValueError(f"unknown side {side!r}")

    filled, cost = _walk(levels, target)
    vwap = cost / filled if filled > ZERO else None
    net: Decimal | None = None
    if vwap is not None and fee.taker is not None:
        net = vwap * (ONE + fee.taker) if side == "buy" else vwap * (ONE - fee.taker)
    return VwapFill(
        venue=book.venue,
        symbol=book.symbol,
        side=side,
        target_qty=target,
        filled_qty=filled,
        vwap=vwap,
        net_price=net,
        fee=fee,
        complete=filled == target,
        fetched_at=book.fetched_at,
    )
