import type { Quote } from "@/lib/api/types";

type KeyFields = Pick<Quote, "source_id" | "city" | "base" | "quote" | "modality" | "branch_id" | "amount_base"> & {
  series_key?: string | null;
};

/**
 * Chave da série de uma cotação (D2). Usa `Quote.series_key`, que o backend sempre emite e que
 * endereça `/v1/history`, `/v1/candles` e `/v1/pregao/stats`. Sem ela (resposta antiga ou fixture),
 * reconstrói `fonte:cidade|digital:BASE/QUOTE:modalidade[:@filial][:montante]`; o sufixo do contexto
 * (hash) não é reproduzido no cliente, então esse fallback só serve para agrupar cotações aqui.
 */
export function quoteKey(q: KeyFields): string {
  if (q.series_key) return q.series_key;
  let key = `${q.source_id}:${q.city ?? "digital"}:${q.base}/${q.quote}:${q.modality}`;
  if (q.branch_id) key += `:@${q.branch_id}`;
  if (q.amount_base) key += `:${q.amount_base}`;
  return key;
}
