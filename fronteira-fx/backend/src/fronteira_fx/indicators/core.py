"""Indicadores técnicos na convenção TA-Lib, implementados em `Decimal` (sem binário TA-Lib, sem numpy/pandas).

Convenções (todas causais: o valor no índice `t` usa só velas de índice ≤ `t`):

* Entrada: sequências alinhadas de `Decimal` (abertura, máxima, mínima, fechamento), da vela mais antiga (índice 0)
  à mais recente. Assume-se que cada vela já está fechada (ver `sinais.apenas_fechadas`).
* Saída: lista do mesmo comprimento da entrada. Índices antes do `lookback` valem `None` (o mesmo que NaN no TA-Lib).
* RSI(14): ganhos e perdas de Wilder. Semente = média simples dos 14 primeiros ∆; depois
  média = (média·13 + valor)/14. RSI = 100·G/(G+P). Sem movimento (G+P = 0) = 50, como no TA-Lib.
  Lookback 14.
* MACD(12, 26, 9): EMA com α = 2/(N+1). EMA26 semeada pela SMA dos 26 primeiros fechamentos. EMA12 começa no índice
  25 (início da lenta), semeada pela SMA dos 12 fechamentos que terminam ali (convenção TA-Lib; difere da EMA12
  semeada no primeiro bar). Linha = EMA12 − EMA26; sinal = EMA9 da linha (semente = SMA dos 9 primeiros valores
  da linha); histograma = linha − sinal. Saídas só a partir do lookback 33.
* Estocástico(5, 3, 3): %K rápido = (C − mín L₅)/(máx H₅ − mín L₅)·100 (0 se máx = mín); %K lento = SMA3 do
  %K rápido; %D = SMA3 do %K lento. Lookback 8.
* ADX(14): TR, +DM e −DM de Wilder na forma de soma (S ← S − S/14 + x), a partir da soma inicial dos 13 primeiros
  valores. +DI = 100·S₊/S_TR; −DI = 100·S₋/S_TR; DX = 100·|+DI − −DI|/(+DI + −DI) (0 se soma nula).
  ADX = média dos 14 primeiros DX, depois (ADX·13 + DX)/14. Lookback 27.
* ATR(14): TR_t = máx(H−L, |H−C_{t−1}|, |L−C_{t−1}|) a partir do índice 1; semente = média dos 14 primeiros TR;
  depois Wilder. Lookback 14. Medido em preço.
* NATR(14) = 100·ATR/C. Lookback 14.
* Ichimoku(9, 26, 52): Tenkan = (máx H₉ + mín L₉)/2; Kijun = (máx H₂₆ + mín L₂₆)/2;
  Senkou A = (Tenkan + Kijun)/2; Senkou B = (máx H₅₂ + mín L₅₂)/2; Chikou = C_t (comparado com C_{t−26}).
  Não existe no TA-Lib: é convenção própria. Os valores são guardados no índice em que são calculados. A
  plotagem deslocada de 26 barras para a frente NÃO é usada em sinais: a nuvem vigente no índice `t` é a
  calculada em `t − 26` (`nuvem_vigente`), que só depende de dados já conhecidos em `t`.

Nada aqui é preço executável nem ordem: são leituras de mercado. Dinheiro e preço ficam em `Decimal`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

HUNDRED = Decimal(100)
ZERO = Decimal(0)
HALF = Decimal("0.5")

RSI_PERIOD = 14
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
STOCH_FASTK = 5
STOCH_SLOWK = 3
STOCH_SLOWD = 3
ADX_PERIOD = 14
ATR_PERIOD = 14
ICHI_TENKAN = 9
ICHI_KIJUN = 26
ICHI_SENKOU_B = 52

LOOKBACK_RSI = RSI_PERIOD
LOOKBACK_MACD = MACD_SLOW - 1 + MACD_SIGNAL - 1
LOOKBACK_STOCH = (STOCH_FASTK - 1) + (STOCH_SLOWK - 1) + (STOCH_SLOWD - 1)
LOOKBACK_ADX = 2 * ADX_PERIOD - 1
LOOKBACK_ATR = ATR_PERIOD
LOOKBACK_NATR = ATR_PERIOD


@dataclass(frozen=True, slots=True)
class Ohlc:
    """Séries alinhadas, da vela mais antiga à mais recente."""

    open: Sequence[Decimal]
    high: Sequence[Decimal]
    low: Sequence[Decimal]
    close: Sequence[Decimal]

    def __post_init__(self) -> None:
        n = len(self.close)
        if not (len(self.open) == len(self.high) == len(self.low) == n):
            raise ValueError("séries OHLC com comprimentos diferentes")
        for i in range(n):
            if self.low[i] > self.high[i]:
                raise ValueError(f"mínima acima da máxima no índice {i}")

    def __len__(self) -> int:
        return len(self.close)


def _sma_seeded_ema(values: Sequence[Decimal | None], period: int) -> list[Decimal | None]:
    """EMA (α = 2/(N+1)) com semente = SMA dos primeiros `period` valores válidos (convenção TA-Lib)."""
    n = len(values)
    out: list[Decimal | None] = [None] * n
    alpha = Decimal(2) / Decimal(period + 1)
    one_minus = 1 - alpha
    valid: list[int] = []
    acc = ZERO
    prev: Decimal | None = None
    for i in range(n):
        v = values[i]
        if v is None:
            continue
        valid.append(i)
        if len(valid) < period:
            acc += v
            continue
        if len(valid) == period:
            acc += v
            prev = acc / Decimal(period)
        else:
            assert prev is not None
            prev = alpha * v + one_minus * prev
        out[i] = prev
    return out


def _sma(values: Sequence[Decimal | None], period: int) -> list[Decimal | None]:
    """SMA sobre valores válidos consecutivos (sem NaN no meio)."""
    n = len(values)
    out: list[Decimal | None] = [None] * n
    window: list[Decimal] = []
    for i in range(n):
        v = values[i]
        if v is None:
            continue
        window.append(v)
        if len(window) > period:
            window.pop(0)
        if len(window) == period:
            out[i] = sum(window, ZERO) / Decimal(period)
    return out


def rsi(close: Sequence[Decimal], period: int = RSI_PERIOD) -> list[Decimal | None]:
    n = len(close)
    out: list[Decimal | None] = [None] * n
    if n <= period:
        return out
    gains = ZERO
    losses = ZERO
    for i in range(1, period + 1):
        d = close[i] - close[i - 1]
        if d > 0:
            gains += d
        else:
            losses -= d
    avg_gain = gains / Decimal(period)
    avg_loss = losses / Decimal(period)
    out[period] = _rsi_value(avg_gain, avg_loss)
    p = Decimal(period)
    for i in range(period + 1, n):
        d = close[i] - close[i - 1]
        g = d if d > 0 else ZERO
        lo = -d if d < 0 else ZERO
        avg_gain = (avg_gain * (p - 1) + g) / p
        avg_loss = (avg_loss * (p - 1) + lo) / p
        out[i] = _rsi_value(avg_gain, avg_loss)
    return out


def _rsi_value(avg_gain: Decimal, avg_loss: Decimal) -> Decimal:
    total = avg_gain + avg_loss
    if total == 0:
        return HALF * HUNDRED
    return HUNDRED * avg_gain / total


@dataclass(frozen=True, slots=True)
class Macd:
    line: list[Decimal | None]
    signal: list[Decimal | None]
    hist: list[Decimal | None]


def macd(close: Sequence[Decimal], fast: int = MACD_FAST, slow: int = MACD_SLOW, signal: int = MACD_SIGNAL) -> Macd:
    n = len(close)
    ema_slow = _sma_seeded_ema(list(close), slow)
    # Convenção TA-Lib: a EMA rápida começa no índice da lenta (slow−1), semeada pela SMA(fast) que termina ali.
    ema_fast: list[Decimal | None] = [None] * n
    if n >= slow:
        alpha_f = Decimal(2) / Decimal(fast + 1)
        prev = sum(close[slow - fast : slow], ZERO) / Decimal(fast)
        ema_fast[slow - 1] = prev
        for i in range(slow, n):
            prev = alpha_f * close[i] + (1 - alpha_f) * prev
            ema_fast[i] = prev
    line: list[Decimal | None] = [
        (f - s) if (f is not None and s is not None) else None for f, s in zip(ema_fast, ema_slow, strict=True)
    ]
    sig = _sma_seeded_ema(line, signal)
    hist: list[Decimal | None] = [
        (m - s) if (m is not None and s is not None) else None for m, s in zip(line, sig, strict=True)
    ]
    # Convenção TA-Lib: as três saídas só existem a partir do lookback completo (33 com 12/26/9).
    lb = slow - 1 + signal - 1
    for i in range(min(lb, len(line))):
        line[i] = None
        sig[i] = None
        hist[i] = None
    return Macd(line=line, signal=sig, hist=hist)


@dataclass(frozen=True, slots=True)
class Stoch:
    k: list[Decimal | None]
    d: list[Decimal | None]


def stoch(
    ohlc: Ohlc,
    fastk: int = STOCH_FASTK,
    slowk: int = STOCH_SLOWK,
    slowd: int = STOCH_SLOWD,
) -> Stoch:
    n = len(ohlc)
    raw: list[Decimal | None] = [None] * n
    for i in range(fastk - 1, n):
        hh = max(ohlc.high[i - fastk + 1 : i + 1])
        ll = min(ohlc.low[i - fastk + 1 : i + 1])
        if hh == ll:
            raw[i] = ZERO
        else:
            raw[i] = (ohlc.close[i] - ll) / (hh - ll) * HUNDRED
    k = _sma(raw, slowk)
    d = _sma(k, slowd)
    # Convenção TA-Lib: %K e %D só existem a partir do lookback completo (8 com 5/3/3).
    lb = (fastk - 1) + (slowk - 1) + (slowd - 1)
    for i in range(min(lb, n)):
        k[i] = None
        d[i] = None
    return Stoch(k=k, d=d)


def true_range(ohlc: Ohlc) -> list[Decimal | None]:
    n = len(ohlc)
    out: list[Decimal | None] = [None] * n
    for i in range(1, n):
        prev_c = ohlc.close[i - 1]
        out[i] = max(ohlc.high[i] - ohlc.low[i], abs(ohlc.high[i] - prev_c), abs(ohlc.low[i] - prev_c))
    return out


def atr(ohlc: Ohlc, period: int = ATR_PERIOD) -> list[Decimal | None]:
    n = len(ohlc)
    out: list[Decimal | None] = [None] * n
    if n <= period:
        return out
    tr = true_range(ohlc)
    p = Decimal(period)
    seed = sum((tr[i] for i in range(1, period + 1)), ZERO) / p  # type: ignore[misc]
    out[period] = seed
    prev = seed
    for i in range(period + 1, n):
        prev = (prev * (p - 1) + tr[i]) / p  # type: ignore[operator]
        out[i] = prev
    return out


def natr(ohlc: Ohlc, period: int = ATR_PERIOD) -> list[Decimal | None]:
    a = atr(ohlc, period)
    out: list[Decimal | None] = [None] * len(ohlc)
    for i, v in enumerate(a):
        if v is not None and ohlc.close[i] != 0:
            out[i] = HUNDRED * v / ohlc.close[i]
    return out


@dataclass(frozen=True, slots=True)
class Adx:
    adx: list[Decimal | None]
    plus_di: list[Decimal | None]
    minus_di: list[Decimal | None]


def adx(ohlc: Ohlc, period: int = ADX_PERIOD) -> Adx:
    n = len(ohlc)
    adx_out: list[Decimal | None] = [None] * n
    pdi_out: list[Decimal | None] = [None] * n
    mdi_out: list[Decimal | None] = [None] * n
    if n <= 2 * period - 1:
        return Adx(adx=adx_out, plus_di=pdi_out, minus_di=mdi_out)
    p = Decimal(period)
    tr_s = ZERO
    pdm_s = ZERO
    mdm_s = ZERO
    # Soma inicial: índices 1 .. period-1 (sem suavização extra).
    for i in range(1, period):
        tr, pdm, mdm = _tr_dm(ohlc, i)
        tr_s += tr
        pdm_s += pdm
        mdm_s += mdm
    dx_seed = ZERO
    dx_count = 0
    prev_adx: Decimal | None = None
    for i in range(period, n):
        tr, pdm, mdm = _tr_dm(ohlc, i)
        tr_s = tr_s - tr_s / p + tr
        pdm_s = pdm_s - pdm_s / p + pdm
        mdm_s = mdm_s - mdm_s / p + mdm
        if tr_s == 0:
            pdi = ZERO
            mdi = ZERO
        else:
            pdi = HUNDRED * pdm_s / tr_s
            mdi = HUNDRED * mdm_s / tr_s
        pdi_out[i] = pdi
        mdi_out[i] = mdi
        dsum = pdi + mdi
        dx = ZERO if dsum == 0 else HUNDRED * abs(pdi - mdi) / dsum
        if prev_adx is None:
            dx_seed += dx
            dx_count += 1
            if dx_count == period:
                prev_adx = dx_seed / p
                adx_out[i] = prev_adx
        else:
            prev_adx = (prev_adx * (p - 1) + dx) / p
            adx_out[i] = prev_adx
    return Adx(adx=adx_out, plus_di=pdi_out, minus_di=mdi_out)


def _tr_dm(ohlc: Ohlc, i: int) -> tuple[Decimal, Decimal, Decimal]:
    h, lo = ohlc.high[i], ohlc.low[i]
    ph, pl, pc = ohlc.high[i - 1], ohlc.low[i - 1], ohlc.close[i - 1]
    tr = max(h - lo, abs(h - pc), abs(lo - pc))
    up = h - ph
    down = pl - lo
    pdm = up if (up > down and up > 0) else ZERO
    mdm = down if (down > up and down > 0) else ZERO
    return tr, pdm, mdm


@dataclass(frozen=True, slots=True)
class Ichimoku:
    """Valores calculados em cada índice (não deslocados). Ver `nuvem_vigente` para o uso em sinais."""

    tenkan: list[Decimal | None]
    kijun: list[Decimal | None]
    senkou_a: list[Decimal | None]
    senkou_b: list[Decimal | None]


def _midpoint(ohlc: Ohlc, period: int) -> list[Decimal | None]:
    n = len(ohlc)
    out: list[Decimal | None] = [None] * n
    for i in range(period - 1, n):
        hh = max(ohlc.high[i - period + 1 : i + 1])
        ll = min(ohlc.low[i - period + 1 : i + 1])
        out[i] = (hh + ll) / 2
    return out


def ichimoku(
    ohlc: Ohlc,
    tenkan: int = ICHI_TENKAN,
    kijun: int = ICHI_KIJUN,
    senkou_b: int = ICHI_SENKOU_B,
) -> Ichimoku:
    t = _midpoint(ohlc, tenkan)
    k = _midpoint(ohlc, kijun)
    sa: list[Decimal | None] = [
        ((a + b) / 2) if (a is not None and b is not None) else None for a, b in zip(t, k, strict=True)
    ]
    sb = _midpoint(ohlc, senkou_b)
    return Ichimoku(tenkan=t, kijun=k, senkou_a=sa, senkou_b=sb)


def nuvem_vigente(ich: Ichimoku, t: int, displacement: int = ICHI_KIJUN) -> tuple[Decimal, Decimal] | None:
    """Limites (A, B) da nuvem que vale no índice `t`: foram calculados em `t − displacement`."""
    src = t - displacement
    if src < 0:
        return None
    a = ich.senkou_a[src]
    b = ich.senkou_b[src]
    if a is None or b is None:
        return None
    return (a, b)
