/**
 * Cartões de preço: um cartão mostra um único contexto (modalidade), nunca a melhor compra de um
 * balcão ao lado da melhor venda de uma conta digital. Referência (BCP, agregadores) fica à parte,
 * e cotações dependentes de montante (simuladores) ficam fora dos cartões.
 */
import type { Currency, Modality, Quote } from "@/lib/api/types";
import { toNumber } from "@/lib/format";

export interface CardContext {
  modality: Modality | null;
  bestBuy: Quote | null;
  bestSell: Quote | null;
  count: number;
  reference: Quote | null;
  otherModalities: Modality[];
}

const MODALITY_PRIORITY: Modality[] = ["cash", "account", "transfer", "card_debit", "card_credit", "card_virtual"];

export function pickCardContext(quotes: Quote[], pair: { base: Currency; quote: Currency }, preferred?: Modality): CardContext {
  const ofPair = quotes.filter((q) => q.base === pair.base && q.quote === pair.quote);
  const reference = ofPair.find((q) => q.kind === "market_reference") ?? null;
  const executable = ofPair.filter((q) => q.kind !== "market_reference" && q.amount_base === null);
  const present = MODALITY_PRIORITY.filter((m) => executable.some((q) => q.modality === m));
  const modality = preferred && present.includes(preferred) ? preferred : (present[0] ?? null);
  if (!modality) return { modality: null, bestBuy: null, bestSell: null, count: 0, reference, otherModalities: [] };
  const group = executable.filter((q) => q.modality === modality);
  let bestBuy: Quote | null = null;
  let bestSell: Quote | null = null;
  for (const q of group) {
    const b = toNumber(q.buy);
    const s = toNumber(q.sell);
    if (b !== null && (bestBuy === null || b > (toNumber(bestBuy.buy) ?? -Infinity))) bestBuy = q;
    if (s !== null && (bestSell === null || s < (toNumber(bestSell.sell) ?? Infinity))) bestSell = q;
  }
  return { modality, bestBuy, bestSell, count: group.length, reference, otherModalities: present.filter((m) => m !== modality) };
}
