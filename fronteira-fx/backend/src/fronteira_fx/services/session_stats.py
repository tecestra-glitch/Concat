"""Resumo da sessão por chave de série: o "dia" começa às 00:00 em `America/Asuncion`.

A fundação (W0A) implementa `ASUNCION` e `day_start_asuncion`; `stats_for_key` e `session_stats` são stubs
tipados que a unidade B5 substitui mantendo as assinaturas.
"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from fronteira_fx.schemas import DataMode
from fronteira_fx.schemas_candles import SessionStats
from fronteira_fx.services.candles import ensure_utc

ASUNCION = ZoneInfo("America/Asuncion")


def day_start_asuncion(now: datetime) -> datetime:
    """00:00 local do dia que contém `now` em Assunção, aware em `ASUNCION` (naive `now` é UTC)."""
    local = ensure_utc(now).astimezone(ASUNCION)
    return datetime(local.year, local.month, local.day, tzinfo=ASUNCION)


def stats_for_key(session: Session, key: str, day_start_utc: datetime, now: datetime, mode: DataMode) -> SessionStats:
    """Stub da fundação: resumo vazio (campos nulos, `n_quotes 0`, `houses 0`). B5 consulta o banco."""
    return SessionStats(key=key, day_start=day_start_asuncion(now), data_mode=mode)


def session_stats(session: Session, keys: list[str], now: datetime, mode: DataMode) -> list[SessionStats]:
    """Uma `SessionStats` por chave, na mesma ordem."""
    now = ensure_utc(now)
    day_start_utc = day_start_asuncion(now).astimezone(UTC)
    return [stats_for_key(session, key, day_start_utc, now, mode) for key in keys]
