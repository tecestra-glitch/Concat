/**
 * Cruzamento BRL/PYG via USD dentro da mesma casa (F14). Puro: recebe pernas e `now`, devolve números
 * como string decimal (§0.8). Arredondamento só na exibição; aqui o corte é `toDecStr(x, 8)`.
 * Informativo, não executável: nenhuma casa oferece este preço, o cálculo é local.
 */
import { toNumber } from "@/lib/format";
import { midOf, toDecStr } from "./candles";
import type { BookLevel } from "./types";

/** Perna mais antiga que isto (24 h) é marcada como `stale`. */
export const STALE_MS = 86_400_000;

export interface Leg {
  buy: string | null;
  sell: string | null;
  captured_at: string;
}

export interface ImpliedCross {
  /** PYG por 1 BRL que a casa paga, passando por USD; `toDecStr(x, 8)`. */
  buy: string | null;
  /** PYG por 1 BRL que a casa cobra, passando por USD; `toDecStr(x, 8)`. */
  sell: string | null;
  /** Algum lado nulo por falta de perna. */
  incomplete: boolean;
  /** Alguma perna com `captured_at` anterior a `now − STALE_MS`. */
  stale: boolean;
  legs: { usdPyg: Leg; usdBrl: Leg };
}

export function legOf(level: BookLevel | null | undefined): Leg | null {
  if (!level) return null;
  return { buy: level.buy, sell: level.sell, captured_at: level.captured_at };
}

/** Data inválida conta como antiga. */
export function isStale(leg: Leg, now: Date): boolean {
  const t = Date.parse(leg.captured_at);
  if (Number.isNaN(t)) return true;
  return t < now.getTime() - STALE_MS;
}

export function midOfLeg(leg: Leg | null): number | null {
  if (!leg) return null;
  return midOf(leg.buy, leg.sell);
}

/** `a / b` como string decimal, ou `null` quando `b` não é positivo ou o resultado não é finito. */
function ratio(a: number | null, b: number | null): string | null {
  if (a === null || b === null || b <= 0) return null;
  const q = a / b;
  return Number.isFinite(q) ? toDecStr(q, 8) : null;
}

export function impliedBrlPyg(usdPyg: Leg, usdBrl: Leg, now: Date): ImpliedCross {
  const buy = ratio(toNumber(usdPyg.buy), toNumber(usdBrl.sell));
  const sell = ratio(toNumber(usdPyg.sell), toNumber(usdBrl.buy));
  return {
    buy,
    sell,
    incomplete: buy === null || sell === null,
    stale: isStale(usdPyg, now) || isStale(usdBrl, now),
    legs: { usdPyg, usdBrl },
  };
}

/** `(direct / implied − 1) · 100`; `null` se algum lado é não numérico ou `implied ≤ 0`. */
export function diffPct(direct: string | null, implied: string | null): number | null {
  const d = toNumber(direct);
  const i = toNumber(implied);
  if (d === null || i === null || i <= 0) return null;
  return (d / i - 1) * 100;
}
