"""Indicadores TA-Lib: valores contra a referência, convenções de borda e Ichimoku por cálculo manual.

A série `fixtures/serie_sintetica_talib.json` é sintética e determinística (não é mercado real). A referência foi
gerada com TA-Lib 0.8.3 em ambiente de verificação; o projeto não depende do TA-Lib.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from fronteira_fx.indicators import core
from fronteira_fx.market.vol import Candle

FIXTURE = Path(__file__).parent / "fixtures" / "serie_sintetica_talib.json"
TOL = Decimal("1e-6")
BASE = datetime(2026, 11, 1, tzinfo=UTC)


def D(x: float | str) -> Decimal:
    return Decimal(str(x))


def candles_de(rows: list[dict]) -> list[Candle]:
    out: list[Candle] = []
    for i, r in enumerate(rows):
        ot = BASE + timedelta(minutes=5 * i)
        out.append(
            Candle(
                open_time=ot,
                close_time=ot + timedelta(minutes=5) - timedelta(seconds=1),
                open=D(r["o"]),
                high=D(r["h"]),
                low=D(r["l"]),
                close=D(r["c"]),
            )
        )
    return out


@pytest.fixture(scope="module")
def ref() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def ohlc(ref: dict) -> core.Ohlc:
    rows = ref["candles"]
    return core.Ohlc(
        open=[D(r["o"]) for r in rows],
        high=[D(r["h"]) for r in rows],
        low=[D(r["l"]) for r in rows],
        close=[D(r["c"]) for r in rows],
    )


def _compara(calc: list[Decimal | None], esperado: list[float | None]) -> None:
    assert len(calc) == len(esperado)
    for i, (c, e) in enumerate(zip(calc, esperado, strict=True)):
        if e is None:
            assert c is None, f"índice {i} deveria ser vazio"
        else:
            assert c is not None, f"índice {i} sem valor"
            assert abs(c - D(e)) < TOL, f"índice {i}: {c} != {e}"


def test_rsi_bate_com_talib(ohlc: core.Ohlc, ref: dict) -> None:
    _compara(core.rsi(list(ohlc.close)), ref["ref"]["rsi14"])


def test_macd_bate_com_talib(ohlc: core.Ohlc, ref: dict) -> None:
    m = core.macd(list(ohlc.close))
    _compara(m.line, ref["ref"]["macd"])
    _compara(m.signal, ref["ref"]["macd_signal"])
    _compara(m.hist, ref["ref"]["macd_hist"])


def test_estocastico_bate_com_talib(ohlc: core.Ohlc, ref: dict) -> None:
    s = core.stoch(ohlc)
    _compara(s.k, ref["ref"]["stoch_k"])
    _compara(s.d, ref["ref"]["stoch_d"])


def test_adx_bate_com_talib(ohlc: core.Ohlc, ref: dict) -> None:
    _compara(core.adx(ohlc).adx, ref["ref"]["adx14"])


def test_atr_e_natr_batem_com_talib(ohlc: core.Ohlc, ref: dict) -> None:
    _compara(core.atr(ohlc), ref["ref"]["atr14"])
    _compara(core.natr(ohlc), ref["ref"]["natr14"])


def test_lookback_como_no_talib(ohlc: core.Ohlc) -> None:
    assert core.LOOKBACK_RSI == 14
    assert core.LOOKBACK_MACD == 33
    assert core.LOOKBACK_STOCH == 8
    assert core.LOOKBACK_ADX == 27
    assert core.LOOKBACK_ATR == 14
    assert next(i for i, v in enumerate(core.adx(ohlc).adx) if v is not None) == core.LOOKBACK_ADX


def test_convencoes_de_borda() -> None:
    flat = [D(10)] * 40
    assert core.rsi(flat)[14] == D(50)
    up = [D(10 + i) for i in range(40)]
    assert core.rsi(up)[14] == D(100)
    down = [D(100 - i) for i in range(40)]
    assert core.rsi(down)[14] == D(0)
    rows = [{"o": 10, "h": 10, "l": 10, "c": 10} for _ in range(40)]
    o = Ohlc_from(rows)
    assert core.stoch(o).k[8] == D(0)
    assert core.adx(o).adx[27] == D(0)
    assert core.atr(o)[14] == D(0)


def Ohlc_from(rows: list[dict]) -> core.Ohlc:
    return core.Ohlc(
        open=[D(r["o"]) for r in rows],
        high=[D(r["h"]) for r in rows],
        low=[D(r["l"]) for r in rows],
        close=[D(r["c"]) for r in rows],
    )


def test_ichimoku_por_calculo_manual() -> None:
    # Faixa linear: H = 100 + i + 2, L = 100 + i - 2 => ponto médio da janela = 100 + (primeiro índice da janela + último)/2
    # com janela [a, b]: (máx H = 100 + b + 2) + (mín L = 100 + a - 2) dividido por 2 = 100 + (a + b)/2.
    rows = [{"o": 100 + i, "h": 102 + i, "l": 98 + i, "c": 100 + i} for i in range(60)]
    ich = core.ichimoku(Ohlc_from(rows))
    assert ich.tenkan[8] == D(100) + D(8 + 0) / 2  # janela [0, 8]: (a+b)/2 = 4
    assert ich.tenkan[8] == D(104)
    assert ich.kijun[25] == D("112.5")  # janela [0, 25]: 100 + (0 + 25)/2
    assert ich.senkou_b[51] == D(100) + D(51) / 2  # janela [0, 51]
    assert ich.senkou_a[25] == (ich.tenkan[25] + ich.kijun[25]) / 2  # type: ignore[operator]
    assert ich.tenkan[7] is None  # janela incompleta
    assert ich.senkou_b[50] is None


def test_nuvem_vigente_usa_calculo_defasado() -> None:
    rows = [{"o": 100 + i, "h": 102 + i, "l": 98 + i, "c": 100 + i} for i in range(90)]
    ich = core.ichimoku(Ohlc_from(rows))
    # Nuvem em t vem do cálculo em t-26: em t=80 usa o índice 54 (Senkou B já completa a partir de 51).
    assert core.nuvem_vigente(ich, 80) == (ich.senkou_a[54], ich.senkou_b[54])  # type: ignore[index]
    # Em t=70 o cálculo de origem é o índice 44, sem Senkou B completa: não há nuvem.
    assert core.nuvem_vigente(ich, 70) is None
    assert core.nuvem_vigente(ich, 25) is None
