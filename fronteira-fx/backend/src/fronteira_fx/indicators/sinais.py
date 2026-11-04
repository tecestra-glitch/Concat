"""Sinais por vela fechada, gravação e checagem de repintura.

Regras:
* Só velas fechadas entram (`apenas_fechadas` descarta a vela ainda aberta, cujo `close_time` é posterior a `agora`).
* O sinal da vela `t` usa indicadores em `t` e `t−1` e a nuvem vigente em `t` (calculada em `t−26`). Nada depende de
  índices futuros, por construção; os testes em `tests/indicators` verificam isso.
* Repintura: o sinal gravado no instante da vela `t` (com dados até `t`) não pode mudar ao recalcular com a série
  completa. `verifica_repintura` faz essa comparação.

Sinais são leituras de mercado. Não são ordem nem preço executável.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from fronteira_fx.indicators import core
from fronteira_fx.market.vol import Candle

RSI_SOBRECOMPRA = Decimal(70)
RSI_SOBREVENDA = Decimal(30)
STOCH_SOBRECOMPRA = Decimal(80)
STOCH_SOBREVENDA = Decimal(20)
ADX_TENDENCIA = Decimal(25)


class VelaInvalidaError(ValueError):
    """Série de velas inconsistente (ordem, OHLC ou intervalo)."""


@dataclass(frozen=True, slots=True)
class Leituras:
    """Indicadores calculados sobre uma série de velas fechadas (todos alinhados ao índice da vela)."""

    rsi: list[Decimal | None]
    macd: core.Macd
    stoch: core.Stoch
    adx: core.Adx
    atr: list[Decimal | None]
    natr: list[Decimal | None]
    ichimoku: core.Ichimoku


@dataclass(frozen=True, slots=True)
class SinalVela:
    """Sinal de uma vela fechada. Todos os campos são de texto ou inteiros, prontos para gravar."""

    indice: int
    close_time: datetime
    rsi_zona: str  # "sobrecompra" | "sobrevenda" | "neutra"
    macd_cruzamento: int  # +1 cruzou para cima, −1 para baixo, 0 sem cruzamento
    stoch_zona: str  # "sobrecompra" | "sobrevenda" | "neutra"
    tendencia: str  # "forte" | "fraca"
    ichimoku_posicao: str  # "acima_nuvem" | "abaixo_nuvem" | "dentro_nuvem"


@dataclass(frozen=True, slots=True)
class RegistroSinal:
    """Sinal como gravado no instante `close_time` da vela, com os dados disponíveis naquele momento."""

    sinal: SinalVela


@dataclass(frozen=True, slots=True)
class Divergencia:
    indice: int
    gravado: SinalVela
    recalculado: SinalVela | None


def valida_velas(candles: Sequence[Candle]) -> None:
    for i, c in enumerate(candles):
        if c.low <= 0 or c.high <= 0 or c.open <= 0 or c.close <= 0:
            raise VelaInvalidaError(f"preço não positivo no índice {i}")
        if c.low > min(c.open, c.close) or c.high < max(c.open, c.close) or c.low > c.high:
            raise VelaInvalidaError(f"OHLC inconsistente no índice {i}")
        if c.open_time >= c.close_time:
            raise VelaInvalidaError(f"intervalo inválido no índice {i}")
        if i and candles[i - 1].open_time >= c.open_time:
            raise VelaInvalidaError(f"velas fora de ordem no índice {i}")


def apenas_fechadas(candles: Sequence[Candle], agora: datetime) -> list[Candle]:
    """Mantém só velas já fechadas em `agora` (close_time ≤ agora)."""
    return [c for c in candles if c.close_time <= agora]


def _ohlc(candles: Sequence[Candle]) -> core.Ohlc:
    return core.Ohlc(
        open=[c.open for c in candles],
        high=[c.high for c in candles],
        low=[c.low for c in candles],
        close=[c.close for c in candles],
    )


def calcula_leituras(candles: Sequence[Candle]) -> Leituras:
    valida_velas(candles)
    ohlc = _ohlc(candles)
    close = list(ohlc.close)
    return Leituras(
        rsi=core.rsi(close),
        macd=core.macd(close),
        stoch=core.stoch(ohlc),
        adx=core.adx(ohlc),
        atr=core.atr(ohlc),
        natr=core.natr(ohlc),
        ichimoku=core.ichimoku(ohlc),
    )


def _zona_rsi(v: Decimal) -> str:
    if v >= RSI_SOBRECOMPRA:
        return "sobrecompra"
    if v <= RSI_SOBREVENDA:
        return "sobrevenda"
    return "neutra"


def _zona_stoch(v: Decimal) -> str:
    if v >= STOCH_SOBRECOMPRA:
        return "sobrecompra"
    if v <= STOCH_SOBREVENDA:
        return "sobrevenda"
    return "neutra"


def sinal_na_vela(candles: Sequence[Candle], leituras: Leituras, t: int) -> SinalVela | None:
    """Sinal da vela `t`, usando só índices ≤ t. None enquanto algum indicador ainda não tem valor."""
    rsi_v = leituras.rsi[t]
    k = leituras.stoch.k[t]
    d_adx = leituras.adx.adx[t]
    ml, ms = leituras.macd.line[t], leituras.macd.signal[t]
    ml_prev = leituras.macd.line[t - 1] if t >= 1 else None
    ms_prev = leituras.macd.signal[t - 1] if t >= 1 else None
    cloud = core.nuvem_vigente(leituras.ichimoku, t)
    if rsi_v is None or k is None or d_adx is None or ml is None or ms is None or cloud is None:
        return None
    if ml_prev is None or ms_prev is None:
        return None
    cruz = 0
    if ml_prev <= ms_prev and ml > ms:
        cruz = 1
    elif ml_prev >= ms_prev and ml < ms:
        cruz = -1
    close = candles[t].close
    top, bottom = max(cloud), min(cloud)
    if close > top:
        pos = "acima_nuvem"
    elif close < bottom:
        pos = "abaixo_nuvem"
    else:
        pos = "dentro_nuvem"
    return SinalVela(
        indice=t,
        close_time=candles[t].close_time,
        rsi_zona=_zona_rsi(rsi_v),
        macd_cruzamento=cruz,
        stoch_zona=_zona_stoch(k),
        tendencia="forte" if d_adx >= ADX_TENDENCIA else "fraca",
        ichimoku_posicao=pos,
    )


def calcula_sinais(candles: Sequence[Candle]) -> list[SinalVela | None]:
    """Sinais de todas as velas, uma lista alinhada à entrada. None onde ainda não há sinal."""
    if not candles:
        return []
    leituras = calcula_leituras(candles)
    return [sinal_na_vela(candles, leituras, t) for t in range(len(candles))]


def grava_em_tempo_real(candles: Sequence[Candle], agora: datetime) -> list[RegistroSinal]:
    """Simula a gravação ao vivo: para cada vela fechada, grava o sinal calculado só com as velas até ela."""
    fechadas = apenas_fechadas(candles, agora)
    registros: list[RegistroSinal] = []
    for k in range(1, len(fechadas) + 1):
        atual = calcula_sinais(fechadas[:k])[k - 1]
        if atual is not None:
            registros.append(RegistroSinal(sinal=atual))
    return registros


def verifica_repintura(gravados: Sequence[RegistroSinal], candles: Sequence[Candle]) -> list[Divergencia]:
    """Compara sinais gravados com o recálculo sobre a série completa. Lista vazia = sem repintura."""
    recalc = calcula_sinais(candles)
    out: list[Divergencia] = []
    for reg in gravados:
        i = reg.sinal.indice
        novo = recalc[i] if 0 <= i < len(recalc) else None
        if novo != reg.sinal:
            out.append(Divergencia(indice=i, gravado=reg.sinal, recalculado=novo))
    return out
