/**
 * DS13 — taxa com casas fixas por grupo (a `formatRate` de src/lib/format.ts varia entre 0 e 2 casas
 * conforme o valor, o que desalinha a coluna). Casa de câmbio em PYG: 0 casas; referência (BCP,
 * agregadores) em PYG: 2 casas; BRL/USD: 4 casas. `decimals` explícito vence o grupo.
 */
import { toNumber } from "@/lib/format";
import type { Currency } from "@/lib/api/types";

export interface RateOptions {
  decimals?: number;
  reference?: boolean;
}

export function rateDecimals(quote: Currency, opts: RateOptions = {}): number {
  if (opts.decimals !== undefined) return opts.decimals;
  if (quote === "PYG") return opts.reference ? 2 : 0;
  return 4;
}

export function formatRateFixed(value: string | number | null | undefined, quote: Currency, opts: RateOptions = {}): string {
  const n = toNumber(value);
  if (n === null) return "—";
  const digits = rateDecimals(quote, opts);
  return new Intl.NumberFormat("pt-BR", { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(n);
}
