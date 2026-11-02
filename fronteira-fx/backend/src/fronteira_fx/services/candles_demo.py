"""Geradores demo determinísticos do pregão (velas, resumo da sessão, sessões das casas).

Em modo `demo` os handlers nunca tocam o banco: usam estes geradores. A fundação (W0A) entrega as
constantes e stubs tipados; a unidade B3 implementa o gerador (FNV-1a + LCG, §0.9) mantendo nomes,
assinaturas e constantes.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from fronteira_fx.schemas_candles import Candle, HouseSession, SessionStats, Timeframe
from fronteira_fx.services.session_stats import day_start_asuncion

DEMO_ANCHOR: dict[str, Decimal] = {"USD/PYG": Decimal("5940"), "USD/BRL": Decimal("5.43"), "BRL/PYG": Decimal("1100")}
DEMO_VOL: dict[str, float] = {"15m": 0.0015, "1h": 0.003, "4h": 0.006, "1d": 0.012}
DEMO_HOUSES: list[dict] = []  # B3 preenche (§0.9)


def demo_candles(key: str, tf: Timeframe, start: datetime | None, end: datetime | None, limit: int) -> list[Candle]:
    """Stub da fundação: nenhuma vela. B3 gera `limit` velas terminando em `bucket_start(end)`."""
    return []


def demo_session_stats(keys: list[str], now: datetime) -> list[SessionStats]:
    """Stub da fundação: uma `SessionStats` vazia por chave (`day_start` em Assunção, `data_mode="demo"`)."""
    day_start = day_start_asuncion(now)
    return [SessionStats(key=key, day_start=day_start, data_mode="demo") for key in keys]


def demo_house_sessions(now: datetime) -> list[HouseSession]:
    """Stub da fundação: nenhuma casa. B3 devolve uma sessão por entrada de `DEMO_HOUSES`."""
    return []
