// Port of `extract_summary` and of the block-page words of backend/src/fronteira_fx/adapters/westernunion.py.
// The page text is untrusted data: these functions only read it with fixed regexes and never execute it.

import { parseDecimalText } from "./decimal.js";

export const BLOCK_WORDS = [
  "access denied",
  "captcha",
  "unusual traffic",
  "pardon our interruption",
  "request blocked",
] as const;

const FEE_RE = /(?:taxa\s+de\s+transfer[êe]ncia|tarifa)\d*[^0-9]{0,20}?([0-9][0-9.,]*)\s*BRL/i;
const LIST_FEE_RE = /\d+\s?%\s+(?:de\s+)?desconto\s+([0-9][0-9.,]*)\s*BRL/i;
const RATE_RE = /1[.,]00\s*BRL\s*=\s*([0-9][0-9.,]*)\s*(?:PYG|Paraguay)/i;
const DELIVERY_RE =
  /(em\s+minutos|minutos|\d+\s*[–-]\s*\d+\s+dias?\s+[úu]teis|\d+\s+dias?\s+[úu]te(?:is|il)|mesmo\s+dia|pr[óo]ximo\s+dia\s+[úu]til)/i;
const PROMO_RE =
  /(\d+\s?%\s+(?:de\s+)?desconto(?:\s+(?:na\s+)?tarifa)?(?:\s+[0-9][0-9.,]*\s*BRL)?|tarifa\s+zero[^|]{0,40})/i;

export interface Summary {
  fee_brl: string | null;
  fee_before_discount_brl: string | null;
  exchange_rate: string | null;
  delivery: string | null;
  promo: string | null;
  summary_text: string;
}

export function extractSummary(bodyText: string): Summary {
  const text = bodyText.replace(/\s+/g, " ");
  const feeMatch = FEE_RE.exec(text);
  const fee = feeMatch?.[1] ? parseDecimalText(feeMatch[1]) : null;
  const listMatch = LIST_FEE_RE.exec(text);
  const listFee = listMatch?.[1] ? parseDecimalText(listMatch[1]) : null;
  const rateMatch = RATE_RE.exec(text);
  const summary = text.includes("RESUMO") ? text.slice(text.indexOf("RESUMO")) : text;
  const deliveryMatch = DELIVERY_RE.exec(summary) ?? DELIVERY_RE.exec(text);
  const promoMatch = PROMO_RE.exec(text);
  return {
    fee_brl: fee,
    fee_before_discount_brl: listFee,
    exchange_rate: rateMatch?.[1] ?? null,
    delivery: deliveryMatch?.[1]?.trim() ?? null,
    promo: promoMatch?.[1]?.trim() ?? null,
    summary_text: summary.slice(0, 1500),
  };
}

export function looksBlocked(text: string): boolean {
  const lower = text.toLowerCase();
  return BLOCK_WORDS.some((w) => lower.includes(w));
}
