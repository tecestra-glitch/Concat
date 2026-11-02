/**
 * Agregação de HistoryPoint → Candle no cliente, com as mesmas regras de bucket do backend (§0.4).
 * Nenhum arredondamento além de `toDecStr(x, 8)` na saída; dinheiro continua string decimal.
 */
import type { Currency, DataMode, HistoryPoint } from "@/lib/api/types";
import { toNumber } from "@/lib/format";
import { PAIRS, TF_SECONDS, type Candle, type PairKey, type Timeframe } from "./types";

/** `x.toFixed(places)` sem zeros à direita nem ponto final; `"-0"` vira `"0"`. */
export function toDecStr(x: number, places = 8): string {
  if (!Number.isFinite(x)) throw new RangeError("número inválido");
  let s = x.toFixed(places);
  if (s.includes(".")) s = s.replace(/0+$/, "").replace(/\.$/, "");
  return s === "-0" ? "0" : s;
}

/** `(buy + sell) / 2` com os dois lados; o lado presente quando só há um; `null` sem nenhum. */
export function midOf(buy: string | null, sell: string | null): number | null {
  const b = toNumber(buy);
  const s = toNumber(sell);
  if (b !== null && s !== null) return (b + s) / 2;
  return b ?? s;
}

/** Início do bucket (ms epoch) alinhado ao epoch Unix em UTC; funciona também antes de 1970. */
export function bucketStart(ms: number, gridS: number): number {
  const g = gridS * 1000;
  return ms - (((ms % g) + g) % g);
}

/** Segmento `[2]` da chave de série (`BASE/QUOTE`) ou `""`. */
export function pairOf(key: string): string {
  return key.split(":")[2] ?? "";
}

export function pairKeyOf(key: string): PairKey | null {
  const p = pairOf(key);
  return (PAIRS as readonly string[]).includes(p) ? (p as PairKey) : null;
}

export function quoteOfPair(pair: PairKey): Currency {
  return pair.split("/")[1] as Currency;
}

export function baseOfPair(pair: PairKey): Currency {
  return pair.split("/")[0] as Currency;
}

interface Bucket {
  ms: number;
  o: number;
  h: number;
  l: number;
  c: number;
  n: number;
  spreadSum: number;
  spreadN: number;
  buyC: number | null;
  sellC: number | null;
}

function flush(b: Bucket, dataMode: DataMode): Candle {
  return {
    t: new Date(b.ms).toISOString(),
    o: toDecStr(b.o),
    h: toDecStr(b.h),
    l: toDecStr(b.l),
    c: toDecStr(b.c),
    n: b.n,
    spread_avg: b.spreadN > 0 ? toDecStr(b.spreadSum / b.spreadN) : null,
    buy_c: b.buyC === null ? null : toDecStr(b.buyC),
    sell_c: b.sellC === null ? null : toDecStr(b.sellC),
    data_mode: dataMode,
  };
}

/**
 * Agrega pontos de 5 min em velas do intervalo `tf` (§0.4). Buckets vazios não são emitidos;
 * `n` conta os pontos com `mid ≠ null` (D33). A entrada não é modificada.
 */
export function aggregateHistory(points: HistoryPoint[], tf: Timeframe, dataMode: DataMode = "real"): Candle[] {
  const grid = TF_SECONDS[tf];
  const sorted = points
    .map((p) => ({ p, ms: Date.parse(p.t) }))
    .filter((x) => !Number.isNaN(x.ms))
    .sort((a, b) => a.ms - b.ms);
  const out: Candle[] = [];
  let cur: Bucket | null = null;
  for (const { p, ms } of sorted) {
    const mid = toNumber(p.mid) ?? midOf(p.buy, p.sell);
    if (mid === null) continue;
    const start = bucketStart(ms, grid);
    if (cur === null || cur.ms !== start) {
      if (cur !== null) out.push(flush(cur, dataMode));
      cur = { ms: start, o: mid, h: mid, l: mid, c: mid, n: 0, spreadSum: 0, spreadN: 0, buyC: null, sellC: null };
    }
    cur.c = mid;
    if (mid > cur.h) cur.h = mid;
    if (mid < cur.l) cur.l = mid;
    cur.n += 1;
    const buy = toNumber(p.buy);
    const sell = toNumber(p.sell);
    if (buy !== null && sell !== null) {
      cur.spreadSum += sell - buy;
      cur.spreadN += 1;
    }
    if (buy !== null) cur.buyC = buy;
    if (sell !== null) cur.sellC = sell;
  }
  if (cur !== null) out.push(flush(cur, dataMode));
  return out;
}

/** Corte pela cauda mantendo a sequência; `limit < 1` → `[]`. */
export function tailLimit<T>(items: T[], limit: number): T[] {
  return limit < 1 ? [] : items.slice(-limit);
}
