"""Volatilidade com exemplos numéricos conferidos à mão (EWMA λ = 0,94, Parkinson, ATR de Wilder, regime)."""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from fronteira_fx.market import vol
from fronteira_fx.market.vol import Candle

T0 = datetime(2026, 11, 4, 0, 0, tzinfo=UTC)


def candle(i: int, o, h, l, c, step: timedelta = timedelta(minutes=5)) -> Candle:  # noqa: E741
    open_time = T0 + step * i
    return Candle(open_time, open_time + step, Decimal(str(o)), Decimal(str(h)), Decimal(str(l)), Decimal(str(c)))


def flat_candles(closes: list[float], step: timedelta = timedelta(minutes=5)) -> list[Candle]:
    return [candle(i, c, c, c, c, step) for i, c in enumerate(closes)]


# ---------------------------------------------------------------- EWMA
def test_ewma_constant_returns_forecast_equals_their_size():
    rets = [Decimal("0.01")] * 21
    # semente = média dos 20 quadrados (1e-4); o 21º retorno não muda nada
    assert float(vol.ewma_next_sigma(rets)) == pytest.approx(0.01, rel=1e-12)


def test_ewma_recursion_by_hand():
    # semente 4e-4 (20 retornos de 0,02); depois 0,94·4e-4 + 0,06·1e-4 = 3,82e-4
    rets = [Decimal("0.02")] * 20 + [Decimal("0.01")]
    assert float(vol.ewma_next_sigma(rets)) == pytest.approx(math.sqrt(3.82e-4), rel=1e-12)


def test_ewma_short_history_uses_all_returns_as_seed():
    assert float(vol.ewma_next_sigma([Decimal("0.03"), Decimal("0.01")])) == pytest.approx(
        math.sqrt((9e-4 + 1e-4) / 2), rel=1e-12
    )
    assert vol.ewma_next_sigma([]) is None


# ---------------------------------------------------------------- Parkinson
def test_parkinson_single_candle_closed_form():
    # H/L = 2 → ln²(2) / (4·1·ln 2) = ln 2 / 4 → σ = √(ln 2 / 4)
    sigma = vol.parkinson_sigma([candle(0, 1, 2, 1, 1.5)])
    assert float(sigma) == pytest.approx(math.sqrt(math.log(2) / 4), rel=1e-12)


def test_parkinson_averages_over_candles():
    # duas velas com H/L = 2 e H/L = 1 (sem range): Σ = ln²2 → σ = √(ln²2 / (4·2·ln2)) = √(ln2/8)
    sigma = vol.parkinson_sigma([candle(0, 1, 2, 1, 1.5), candle(1, 1, 1, 1, 1)])
    assert float(sigma) == pytest.approx(math.sqrt(math.log(2) / 8), rel=1e-12)
    assert vol.parkinson_sigma([]) is None


# ---------------------------------------------------------------- ATR
def test_atr_constant_true_range():
    # 15 velas com faixa 2 e fechamento 100: cada TR = 2 → ATR(14) = 2
    candles = [candle(i, 100, 101, 99, 100) for i in range(15)]
    assert vol.atr(candles) == Decimal(2)


def test_atr_wilder_smoothing_after_a_gap():
    # 16 velas: a última abre um salto (H 110, L 108) com fechamento anterior 100 → TR = 10
    # ATR = (2·13 + 10) / 14 = 36/14
    candles = [candle(i, 100, 101, 99, 100) for i in range(15)] + [candle(15, 109, 110, 108, 109)]
    assert vol.atr(candles) == Decimal(36) / Decimal(14)


def test_atr_needs_period_plus_one_candles():
    assert vol.atr([candle(i, 100, 101, 99, 100) for i in range(14)]) is None


def test_true_range_uses_previous_close_for_gaps_down():
    # vela 0 fecha em 100; velas 1..14 com H 91 e L 89 e fechamento 90
    # TR1 = máx(2, |91−100|=9, |89−100|=11) = 11; TR2..TR14 = máx(2, 1, 1) = 2
    # semente de Wilder = média dos 14 primeiros TR = (11 + 13·2) / 14 = 37/14
    candles = [candle(0, 100, 100, 100, 100)] + [candle(i, 90, 91, 89, 90) for i in range(1, 15)]
    assert vol.atr(candles, period=14) == Decimal(37) / Decimal(14)


# ---------------------------------------------------------------- estado e alerta
def _noisy_closes(n: int, amp: float = 0.001) -> list[float]:
    return [100 * (1 + amp * (1 if i % 2 else -1)) for i in range(n)]


def _daily(n: int = 20) -> list[Candle]:
    base = T0 - timedelta(days=n)
    out = []
    for i in range(n):
        o = Decimal("100")
        out.append(Candle(base + timedelta(days=i), base + timedelta(days=i + 1), o, Decimal("102"), Decimal("99"), o))
    return out


NOW = T0 + timedelta(minutes=5 * 60) + timedelta(seconds=30)


def test_insufficient_data_when_too_few_candles():
    snap = vol.snapshot("X/Y", flat_candles([100.0] * 10), _daily(), now=NOW)
    assert snap.status == "insufficient_data" and snap.regime is None and snap.alert is False


def test_stale_input_when_the_last_candle_is_old():
    closes = _noisy_closes(60)
    snap = vol.snapshot("X/Y", flat_candles(closes), _daily(), now=NOW + timedelta(hours=3))
    assert snap.status == "stale_input" and snap.alert is False


def test_quiet_market_is_normal_without_alert():
    closes = _noisy_closes(60)
    c5 = [candle(i, c, c, c, c) for i, c in enumerate(closes)]  # H = L: sem faixa intravela
    snap = vol.snapshot("X/Y", c5, _daily(), now=T0 + timedelta(minutes=5 * 60) + timedelta(seconds=30))
    assert snap.status == "ok"
    assert snap.regime == "normal" and snap.alert is False and snap.reasons == ()
    assert snap.ewma_pct_5m is not None and snap.ewma_pct_5m > 0


def test_jump_beyond_three_times_ewma_is_a_muito_alta_alert():
    closes = _noisy_closes(60) + [110.0]  # salto de +10 % contra σ ≈ 0,1 %
    c5 = [candle(i, c, c, c, c) for i, c in enumerate(closes)]
    snap = vol.snapshot("X/Y", c5, _daily(), now=T0 + timedelta(minutes=5 * 61) + timedelta(seconds=30))
    assert snap.status == "ok" and snap.alert is True
    assert snap.regime == "muito_alta"
    assert "movimento_acima_de_3x_ewma" in snap.reasons
    assert snap.last_move_pct is not None and snap.last_move_pct > 9


def test_regime_ratio_above_two_is_an_alert_even_without_a_jump():
    # 5 min com faixa larga em todas as velas; diárias com faixa pequena → 1 dia / 20 dias > 2
    closes = _noisy_closes(300)
    c5 = [candle(i, c, c * 1.05, c * 0.95, c) for i, c in enumerate(closes)]
    daily = [
        Candle(c.open_time, c.close_time, c.open, c.open * Decimal("1.001"), c.open * Decimal("0.999"), c.close)
        for c in _daily()
    ]
    snap = vol.snapshot("X/Y", c5, daily, now=T0 + timedelta(minutes=5 * 300) + timedelta(seconds=30))
    assert snap.ratio_1d_20d is not None and snap.ratio_1d_20d >= 2
    assert snap.alert is True and "regime_1d_acima_de_2x_20d" in snap.reasons and snap.regime == "muito_alta"


def test_atr_is_reported_in_price_units():
    closes = _noisy_closes(60)
    c5 = [candle(i, c, c + 0.5, c - 0.5, c) for i, c in enumerate(closes)]
    snap = vol.snapshot("X/Y", c5, _daily(), now=T0 + timedelta(minutes=5 * 60) + timedelta(seconds=30))
    assert snap.atr_14_5m is not None and snap.atr_14_5m > 0
    assert snap.atr_14_5m < 2  # faixa de 1,0 + saltos pequenos do ruído
