"""Resumo da sessão por chave de série: o "dia" começa às 00:00 em `America/Asuncion`.

Cada cotação com `mid` conta no dia: `open`/`high`/`low`/`last` são o primeiro, o máximo, o mínimo e o último
`mid` entre `day_start` e `now`. `spread_avg` é a média de `sell − buy` nas cotações com os dois lados e
`houses` conta as casas (não referências) que cotam o mesmo par no mesmo dia. Nada aqui é negócio fechado.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from fronteira_fx.models import Quote
from fronteira_fx.schemas import DataMode
from fronteira_fx.schemas_candles import SessionStats
from fronteira_fx.services.candles import ensure_utc, key_filter, mid_of, pair_of

ASUNCION = ZoneInfo("America/Asuncion")


def day_start_asuncion(now: datetime) -> datetime:
    """00:00 local do dia que contém `now` em Assunção, aware em `ASUNCION` (naive `now` é UTC)."""
    local = ensure_utc(now).astimezone(ASUNCION)
    return datetime(local.year, local.month, local.day, tzinfo=ASUNCION)


def houses_for_pair(session: Session, pair: str, day_start_utc: datetime, now: datetime, mode: DataMode) -> int:
    """Casas distintas (não referência) com cotação do par `BASE/QUOTE` na janela `[day_start, now]`."""
    base, sep, quote = pair.partition("/")
    if not sep:
        return 0
    stmt = select(func.count(func.distinct(Quote.source_id))).where(
        Quote.data_mode == mode,
        Quote.kind != "market_reference",
        Quote.base == base,
        Quote.quote == quote,
        Quote.captured_at >= day_start_utc,
        Quote.captured_at <= now,
    )
    return session.scalar(stmt) or 0


def stats_for_key(session: Session, key: str, day_start_utc: datetime, now: datetime, mode: DataMode) -> SessionStats:
    """Resumo do dia da chave: cotações sem nenhum lado são ignoradas (inclusive em `n_quotes`)."""
    now = ensure_utc(now)
    stmt = (
        select(Quote)
        .where(
            key_filter(key),
            Quote.data_mode == mode,
            Quote.captured_at >= day_start_utc,
            Quote.captured_at <= now,
        )
        .order_by(Quote.captured_at.asc(), Quote.id.asc())
    )
    first: Decimal | None = None
    high: Decimal | None = None
    low: Decimal | None = None
    last: Decimal | None = None
    last_at: datetime | None = None
    n_quotes = 0
    spread_sum = Decimal(0)
    spread_n = 0
    for quote in session.scalars(stmt):
        mid = mid_of(quote.buy, quote.sell)
        if mid is None:
            continue
        first = mid if first is None else first
        high = mid if high is None or mid > high else high
        low = mid if low is None or mid < low else low
        last = mid
        last_at = ensure_utc(quote.captured_at)
        n_quotes += 1
        if quote.buy is not None and quote.sell is not None:
            spread_sum += quote.sell - quote.buy
            spread_n += 1

    change_abs: Decimal | None = None
    change_pct: Decimal | None = None
    if first is not None and last is not None:
        change_abs = last - first
        if first != 0:
            change_pct = (last - first) / first * 100
    spread_avg = spread_sum / spread_n if spread_n else None

    return SessionStats(
        key=key,
        day_start=day_start_asuncion(now),
        open=first,
        high=high,
        low=low,
        last=last,
        last_at=last_at,
        change_abs=change_abs,
        change_pct=change_pct,
        n_quotes=n_quotes,
        spread_avg=spread_avg,
        houses=houses_for_pair(session, pair_of(key), day_start_utc, now, mode),
        data_mode=mode,
    )


def session_stats(session: Session, keys: list[str], now: datetime, mode: DataMode) -> list[SessionStats]:
    """Uma `SessionStats` por chave, na mesma ordem; o dia é o de `now` em Assunção."""
    now = ensure_utc(now)
    day_start_utc = day_start_asuncion(now).astimezone(UTC)
    return [stats_for_key(session, key, day_start_utc, now, mode) for key in keys]
