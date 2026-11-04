"""Volatilidade de referência (módulo `market`): EWMA (λ = 0,94), Parkinson e ATR(14).

Funções puras sobre velas e retornos, em `Decimal`; sem I/O e sem relógio (o `now` entra por parâmetro).

* EWMA (RiskMetrics): σ²ₜ₊₁ = λ·σ²ₜ + (1−λ)·rₜ². A variância semente é a média dos quadrados dos primeiros
  `SEED_N` retornos; o restante rola a recorrência. O valor devolvido é a previsão para o próximo retorno.
* Parkinson (1980): σ = √( Σ ln(Hᵢ/Lᵢ)² / (4·n·ln 2) ), por vela (sem anualizar).
* ATR(14) (Wilder): TR = máx(H−L, |H−Fₚ|, |L−Fₚ|); semente = média dos 14 primeiros TR; depois
  ATRₜ = (ATRₜ₋₁·13 + TRₜ) / 14. Medida em preço.
* Regime: a volatilidade de 1 dia (Parkinson das velas de 5 min × √288, escala pela raiz do tempo) dividida
  pela de 20 dias (Parkinson das velas diárias). Limiares de partida, a calibrar com dados reais.

Os retornos são logarítmicos entre velas fechadas. Nada aqui é preço executável.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Literal

LAMBDA = Decimal("0.94")
SEED_N = 20
LN2 = Decimal(2).ln()
ATR_PERIOD = 14
GRID_5M = 300
SHORT_5M_PER_DAY = 288  # 24 h de velas de 5 min
LONG_DAYS = 20
MIN_5M_CANDLES = 30  # ~2,5 h de velas fechadas: abaixo disso não há EWMA com sentido
MOVE_ALERT_X = Decimal(3)  # |retorno| > 3 × EWMA
REGIME_ALERT_X = Decimal(2)  # 1 dia / 20 dias > 2
REGIME_ALTA_X = Decimal("1.5")
MOVE_ALTA_X = Decimal(2)

Status = Literal["ok", "insufficient_data", "stale_input"]
Regime = Literal["normal", "alta", "muito_alta"]


@dataclass(frozen=True, slots=True)
class Candle:
    open_time: datetime
    close_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal


def log_returns(closes: Sequence[Decimal]) -> list[Decimal]:
    """ln(cₜ / cₜ₋₁) entre preços consecutivos positivos."""
    out: list[Decimal] = []
    for prev, cur in zip(closes, closes[1:], strict=False):
        if prev > 0 and cur > 0:
            out.append((cur / prev).ln())
    return out


def ewma_next_sigma(returns: Sequence[Decimal], lam: Decimal = LAMBDA, seed_n: int = SEED_N) -> Decimal | None:
    """Desvio previsto para o próximo retorno, dado o histórico `returns` (RiskMetrics)."""
    if not returns:
        return None
    k = min(len(returns), seed_n)
    var = sum((r * r for r in returns[:k]), Decimal(0)) / Decimal(k)
    for r in returns[k:]:
        var = lam * var + (1 - lam) * r * r
    return var.sqrt()


def parkinson_sigma(candles: Sequence[Candle]) -> Decimal | None:
    """Parkinson por vela: √( Σ ln(H/L)² / (4·n·ln 2) ). Não anualizado."""
    n = len(candles)
    if n == 0:
        return None
    total = Decimal(0)
    for c in candles:
        if c.low <= 0 or c.high <= 0:
            return None
        total += (c.high / c.low).ln() ** 2
    return (total / (4 * n * LN2)).sqrt()


def atr(candles: Sequence[Candle], period: int = ATR_PERIOD) -> Decimal | None:
    """ATR de Wilder sobre `period` velas (precisa de period + 1 velas para o primeiro TR)."""
    if len(candles) < period + 1:
        return None
    trs: list[Decimal] = []
    for prev, cur in zip(candles, candles[1:], strict=False):
        trs.append(max(cur.high - cur.low, abs(cur.high - prev.close), abs(cur.low - prev.close)))
    value = sum(trs[:period], Decimal(0)) / Decimal(period)
    for tr in trs[period:]:
        value = (value * (period - 1) + tr) / Decimal(period)
    return value


@dataclass(frozen=True, slots=True)
class VolatilitySnapshot:
    instrument: str
    status: Status
    as_of: datetime | None
    last_close: Decimal | None = None
    last_move_pct: Decimal | None = None  # último retorno de 5 min, em %
    ewma_pct_5m: Decimal | None = None  # desvio previsto do próximo retorno de 5 min, em %
    parkinson_1d_pct: Decimal | None = None  # 1 dia (velas de 5 min, escala √288), em %
    parkinson_20d_pct: Decimal | None = None  # 20 dias (velas diárias), em %
    ratio_1d_20d: Decimal | None = None
    atr_14_5m: Decimal | None = None  # em preço
    regime: Regime | None = None
    alert: bool = False
    reasons: tuple[str, ...] = field(default_factory=tuple)


def _pct(x: Decimal | None) -> Decimal | None:
    return None if x is None else x * 100


def snapshot(
    instrument: str,
    candles_5m: Sequence[Candle],
    candles_1d: Sequence[Candle],
    *,
    now: datetime,
) -> VolatilitySnapshot:
    """Estado de volatilidade de um instrumento a partir de velas já fechadas."""
    c5 = sorted(candles_5m, key=lambda c: c.open_time)
    c1 = sorted(candles_1d, key=lambda c: c.open_time)
    if len(c5) < MIN_5M_CANDLES or len(c1) < LONG_DAYS:
        as_of = c5[-1].close_time if c5 else None
        return VolatilitySnapshot(instrument, "insufficient_data", as_of)
    last = c5[-1]
    if now - last.close_time > timedelta(seconds=2 * GRID_5M):
        return VolatilitySnapshot(instrument, "stale_input", last.close_time, last_close=last.close)

    rets = log_returns([c.close for c in c5])
    last_move = rets[-1]
    sigma_prev = ewma_next_sigma(rets[:-1])  # previsão feita antes do último retorno (sem olhar o futuro)
    sigma_next = ewma_next_sigma(rets)
    short_sigma = parkinson_sigma(c5[-SHORT_5M_PER_DAY:])
    long_sigma = parkinson_sigma(c1[-LONG_DAYS:])
    short_day = short_sigma * Decimal(SHORT_5M_PER_DAY).sqrt() if short_sigma is not None else None
    ratio = short_day / long_sigma if short_day is not None and long_sigma and long_sigma > 0 else None

    reasons: list[str] = []
    move_alert = bool(sigma_prev and sigma_prev > 0 and abs(last_move) > MOVE_ALERT_X * sigma_prev)
    regime_alert = ratio is not None and ratio >= REGIME_ALERT_X
    if move_alert:
        reasons.append("movimento_acima_de_3x_ewma")
    if regime_alert:
        reasons.append("regime_1d_acima_de_2x_20d")
    move_alta = bool(sigma_prev and sigma_prev > 0 and abs(last_move) > MOVE_ALTA_X * sigma_prev)
    alta = (ratio is not None and ratio >= REGIME_ALTA_X) or move_alta
    regime: Regime = "muito_alta" if (move_alert or regime_alert) else ("alta" if alta else "normal")
    return VolatilitySnapshot(
        instrument=instrument,
        status="ok",
        as_of=last.close_time,
        last_close=last.close,
        last_move_pct=_pct(last_move),
        ewma_pct_5m=_pct(sigma_next),
        parkinson_1d_pct=_pct(short_day),
        parkinson_20d_pct=_pct(long_sigma),
        ratio_1d_20d=ratio,
        atr_14_5m=atr(c5),
        regime=regime,
        alert=move_alert or regime_alert,
        reasons=tuple(reasons),
    )
