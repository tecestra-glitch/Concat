"""Velas OHLC do `mid` por chave de série e intervalo (15m, 1h, 4h, 1d), alinhadas ao epoch UTC.

Cada casa publica Compra e Venda; a vela resume o `mid = (buy + sell) / 2` das cotações publicadas no
bucket. Nada aqui é negócio fechado. Sem arredondamento na agregação: `Decimal` com precisão 28 e saída
normalizada por `fmt` (8 casas, ROUND_HALF_EVEN, sem zeros à direita).
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from fronteira_fx.decimal_utils import fmt
from fronteira_fx.models import Quote
from fronteira_fx.schemas import DataMode
from fronteira_fx.schemas_candles import TF_SECONDS, Candle, CandleSeries, Timeframe

__all__ = [
    "aggregate_quotes",
    "bucket_start",
    "candles_series",
    "default_window",
    "ensure_utc",
    "fmt",
    "key_filter",
    "mid_of",
    "pair_of",
]


def ensure_utc(ts: datetime) -> datetime:
    """Datetime aware em UTC: naive é tratado como UTC; aware é convertido."""
    if ts.tzinfo is None:
        return ts.replace(tzinfo=UTC)
    return ts.astimezone(UTC)


def bucket_start(ts: datetime, grid_s: int) -> datetime:
    """Início do bucket de `grid_s` segundos que contém `ts`, alinhado ao epoch Unix (dia = 00:00Z)."""
    epoch = math.floor(ensure_utc(ts).timestamp())
    return datetime.fromtimestamp(epoch - epoch % grid_s, tz=UTC)


def mid_of(buy: Decimal | None, sell: Decimal | None) -> Decimal | None:
    """Média dos dois lados; o lado presente quando só há um; `None` quando não há nenhum."""
    if buy is not None and sell is not None:
        return (buy + sell) / 2
    return buy if buy is not None else sell


def pair_of(key: str) -> str:
    """Segmento `[2]` da chave (`BASE/QUOTE`) ou `""` quando ausente."""
    parts = key.split(":")
    return parts[2] if len(parts) > 2 else ""


def key_filter(key: str):
    """Chave exata ou qualquer série abaixo dela (`:@branch`, `:amount`, `:ctx`), como no contrato."""
    return (Quote.series_key == key) | Quote.series_key.like(key.replace("%", r"\%") + ":%")


def _norm(value: Decimal) -> Decimal:
    """Decimal com a mesma representação da apresentação (`fmt`), sem passar por float."""
    return Decimal(cast(str, fmt(value)))  # `fmt` só devolve None para None


def _norm_opt(value: Decimal | None) -> Decimal | None:
    return None if value is None else _norm(value)


@dataclass(slots=True)
class _Bucket:
    t: datetime
    o: Decimal
    h: Decimal
    l: Decimal  # noqa: E741
    c: Decimal
    n: int = 0
    spread_sum: Decimal = Decimal(0)
    spread_n: int = 0
    buy_c: Decimal | None = None
    sell_c: Decimal | None = None

    def add(self, quote: Quote, mid: Decimal) -> None:
        if self.n:
            self.h = max(self.h, mid)
            self.l = min(self.l, mid)
            self.c = mid
        self.n += 1
        if quote.buy is not None and quote.sell is not None:
            self.spread_sum += quote.sell - quote.buy
            self.spread_n += 1
        if quote.buy is not None:
            self.buy_c = quote.buy
        if quote.sell is not None:
            self.sell_c = quote.sell

    def to_candle(self, mode: DataMode) -> Candle:
        spread_avg = self.spread_sum / self.spread_n if self.spread_n else None
        return Candle(
            t=self.t,
            o=_norm(self.o),
            h=_norm(self.h),
            l=_norm(self.l),
            c=_norm(self.c),
            n=self.n,
            spread_avg=_norm_opt(spread_avg),
            buy_c=_norm_opt(self.buy_c),
            sell_c=_norm_opt(self.sell_c),
            data_mode=mode,
        )


def aggregate_quotes(quotes: Iterable[Quote], tf: Timeframe, mode: DataMode) -> list[Candle]:
    """Agrupa cotações (ordenadas por `captured_at`, `id`) em velas por `bucket_start`; buckets vazios não existem.

    Cotações sem nenhum lado (`mid_of == None`) são ignoradas. Por bucket: `o` primeiro `mid`, `c` último,
    `h`/`l` extremos, `n` cotações com `mid`, `spread_avg` média de `sell − buy` nas cotações com os dois lados,
    `buy_c`/`sell_c` último lado não nulo. Saída ascendente por `t`, sem `t` repetido.
    """
    grid_s = TF_SECONDS[tf]
    buckets: dict[datetime, _Bucket] = {}
    for quote in sorted(quotes, key=lambda q: ensure_utc(q.captured_at)):
        mid = mid_of(quote.buy, quote.sell)
        if mid is None:
            continue
        t = bucket_start(quote.captured_at, grid_s)
        bucket = buckets.get(t)
        if bucket is None:
            bucket = buckets[t] = _Bucket(t=t, o=mid, h=mid, l=mid, c=mid)
        bucket.add(quote, mid)
    return [buckets[t].to_candle(mode) for t in sorted(buckets)]


def default_window(
    tf: Timeframe, start: datetime | None, end: datetime | None, limit: int, now: datetime
) -> tuple[datetime, datetime]:
    """Janela efetiva `(from_eff, to)` em UTC: `to = end or now`; `from = start or bucket_start(to) − (limit − 1)·grid`;
    `from_eff = bucket_start(from)`. `from` é inclusivo e `to` exclusivo sobre `captured_at`."""
    grid_s = TF_SECONDS[tf]
    until = ensure_utc(end) if end is not None else ensure_utc(now)
    if start is None:
        since = bucket_start(until, grid_s) - timedelta(seconds=(limit - 1) * grid_s)
    else:
        since = ensure_utc(start)
    return bucket_start(since, grid_s), until


def candles_series(
    session: Session,
    key: str,
    tf: Timeframe,
    start: datetime | None,
    end: datetime | None,
    limit: int,
    mode: DataMode,
) -> CandleSeries:
    """Consulta as cotações da chave (casamento por prefixo) no modo e agrega; corta pela cauda (`candles[-limit:]`).

    Não valida `start >= end`: o handler faz isso.
    """
    from_eff, until = default_window(tf, start, end, limit, datetime.now(UTC))
    stmt = (
        select(Quote)
        .where(key_filter(key), Quote.data_mode == mode, Quote.captured_at >= from_eff, Quote.captured_at < until)
        .order_by(Quote.captured_at.asc(), Quote.id.asc())
    )
    candles = aggregate_quotes(session.scalars(stmt), tf, mode)
    tail = candles[-limit:] if limit > 0 else []
    return CandleSeries(key=key, tf=tf, candles=tail, data_mode=mode)
