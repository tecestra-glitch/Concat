/**
 * Indicadores técnicos sobre velas do pregão (F12). Funções puras: sem DOM, sem React, sem dependências.
 * Os decimais das velas (strings) só viram número no cálculo. Toda série de saída tem o mesmo comprimento
 * da entrada e traz `null` onde o indicador ainda não existe.
 */
import { INDICATOR_PERIODS, type Candle, type ChartOverlays, type IndicatorState, type Series } from "./types";

function assertPeriod(period: number): void {
  if (!Number.isInteger(period) || period < 1) throw new RangeError("period deve ser inteiro ≥ 1");
}

/** Fechamentos como número (`Number(c.c)`), na ordem das velas. */
export function closes(candles: Candle[]): number[] {
  return candles.map((c) => Number(c.c));
}

/** Média móvel simples. Um `null` na entrada anula as `period − 1` saídas seguintes. */
export function sma(values: Series, period: number): Series {
  assertPeriod(period);
  const out: Series = values.map(() => null);
  let run = 0;
  for (let i = 0; i < values.length; i++) {
    if (values[i] === null) {
      run = 0;
      continue;
    }
    run++;
    if (run < period) continue;
    let sum = 0;
    for (let j = i - period + 1; j <= i; j++) sum += values[j] ?? 0;
    out[i] = sum / period;
  }
  return out;
}

/** Média móvel exponencial: semente = SMA da primeira janela completa; recalculada após cada `null`. */
export function ema(values: Series, period: number): Series {
  assertPeriod(period);
  const out: Series = values.map(() => null);
  let run = 0;
  let prev = 0;
  for (let i = 0; i < values.length; i++) {
    const x = values[i];
    if (x === null) {
      run = 0;
      continue;
    }
    run++;
    if (run === period) {
      let sum = 0;
      for (let j = i - period + 1; j <= i; j++) sum += values[j] ?? 0;
      prev = sum / period;
      out[i] = prev;
    } else if (run > period) {
      prev = prev + ((x - prev) * 2) / (period + 1);
      out[i] = prev;
    }
  }
  return out;
}

/** Bandas de Bollinger: `middle` = SMA; desvio-padrão populacional da mesma janela; bandas = middle ± k·std. */
export function bollinger(values: Series, period = 20, k = 2): { middle: Series; upper: Series; lower: Series } {
  const middle = sma(values, period);
  const upper: Series = values.map(() => null);
  const lower: Series = values.map(() => null);
  for (let i = 0; i < values.length; i++) {
    const m = middle[i];
    if (m === null) continue;
    let sq = 0;
    for (let j = i - period + 1; j <= i; j++) {
      const d = (values[j] ?? 0) - m;
      sq += d * d;
    }
    const std = Math.sqrt(sq / period);
    upper[i] = m + k * std;
    lower[i] = m - k * std;
  }
  return { middle, upper, lower };
}

/**
 * Average True Range de Wilder. `tr[0] = h − l`; depois o maior entre `h − l`, `|h − c anterior|` e
 * `|l − c anterior|`. A primeira saída é a média simples dos primeiros `period` TR; depois, suavização de Wilder.
 */
export function atr(candles: Candle[], period = 14): Series {
  assertPeriod(period);
  const tr: number[] = [];
  let prevClose = 0;
  for (const c of candles) {
    const h = Number(c.h);
    const l = Number(c.l);
    const range = h - l;
    tr.push(tr.length === 0 ? range : Math.max(range, Math.abs(h - prevClose), Math.abs(l - prevClose)));
    prevClose = Number(c.c);
  }
  const out: Series = tr.map(() => null);
  let prev = 0;
  for (let i = 0; i < tr.length; i++) {
    if (i < period - 1) continue;
    if (i === period - 1) {
      let sum = 0;
      for (let j = 0; j < period; j++) sum += tr[j] ?? 0;
      prev = sum / period;
    } else {
      prev = (prev * (period - 1) + (tr[i] ?? 0)) / period;
    }
    out[i] = prev;
  }
  return out;
}

/**
 * VWAP proxy: preço típico `(h + l + c) / 3` ponderado por `n`, com acumuladores zerados a cada dia UTC.
 * proxy: `n` conta atualizações de cotação, não volume negociado. Não é rótulo de interface.
 * `n ≤ 0` → `null` na vela, sem alterar o acumulado.
 */
export function vwapProxy(candles: Candle[]): Series {
  const out: Series = [];
  let num = 0;
  let den = 0;
  let day = "";
  for (const c of candles) {
    const d = c.t.slice(0, 10);
    if (d !== day) {
      num = 0;
      den = 0;
      day = d;
    }
    if (c.n <= 0) {
      out.push(null);
      continue;
    }
    const tp = (Number(c.h) + Number(c.l) + Number(c.c)) / 3;
    num += tp * c.n;
    den += c.n;
    out.push(num / den);
  }
  return out;
}

/** Overlays do gráfico: só as chaves dos indicadores ligados. `volume` não gera overlay (é o histograma). */
export function buildOverlays(candles: Candle[], state: IndicatorState): ChartOverlays {
  const cl = closes(candles);
  const overlays: ChartOverlays = {};
  if (state.sma) overlays.sma = sma(cl, INDICATOR_PERIODS.sma);
  if (state.ema) overlays.ema = ema(cl, INDICATOR_PERIODS.ema);
  if (state.bollinger) {
    const b = bollinger(cl, INDICATOR_PERIODS.bollinger.period, INDICATOR_PERIODS.bollinger.k);
    overlays.bbUpper = b.upper;
    overlays.bbLower = b.lower;
  }
  return overlays;
}
