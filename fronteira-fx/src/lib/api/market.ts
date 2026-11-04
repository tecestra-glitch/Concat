/**
 * Módulo `market` (docs/api-contract.md, seção «Mercado»): manchetes, referências de mercado e volatilidade.
 * Tudo aqui é REFERÊNCIA: `executable` é sempre `false` e nada disto é preço de casa de câmbio.
 * O texto das manchetes vem de feeds públicos: é dado não confiável, sempre exibido como texto escapado.
 */
import { z } from "zod";
import { DecimalString, ModeSchema } from "./schemas";

export const NewsItemSchema = z.object({
  id: z.string(),
  source: z.string(),
  feed: z.string(),
  title: z.string(),
  link: z.string(),
  /** Trecho curto, só em feed que autoriza (hoje investinglive); null nos demais. Texto de terceiros: escapado. */
  excerpt: z.string().nullable(),
  /** Atribuição da fonte: sempre presente e exibida junto de cada item. */
  attribution: z.string(),
  published_at: z.string().nullable(),
  captured_at: z.string(),
  data_mode: ModeSchema,
});

export const MarketQuoteKindSchema = z.enum(["crypto", "fx_reference", "bcb_series"]);

export const MarketQuoteSchema = z.object({
  instrument: z.string(),
  label: z.string(),
  kind: MarketQuoteKindSchema,
  source: z.string(),
  price: DecimalString,
  change_pct: DecimalString.nullable(),
  observed_at: z.string(),
  captured_at: z.string(),
  executable: z.literal(false),
  note: z.string(),
  data_mode: ModeSchema,
});

export const VolatilityStatusSchema = z.enum(["ok", "insufficient_data", "stale_input"]);
export const RegimeSchema = z.enum(["normal", "alta", "muito_alta"]);

export const MarketVolatilitySchema = z.object({
  instrument: z.string(),
  status: VolatilityStatusSchema,
  as_of: z.string().nullable(),
  last_close: DecimalString.nullable(),
  last_move_pct: DecimalString.nullable(),
  ewma_pct_5m: DecimalString.nullable(),
  parkinson_1d_pct: DecimalString.nullable(),
  parkinson_20d_pct: DecimalString.nullable(),
  ratio_1d_20d: DecimalString.nullable(),
  atr_14_5m: DecimalString.nullable(),
  regime: RegimeSchema.nullable(),
  alert: z.boolean(),
  reasons: z.array(z.string()),
  data_mode: ModeSchema,
});

export const NewsListSchema = z.array(NewsItemSchema);
export const MarketQuoteListSchema = z.array(MarketQuoteSchema);
export const MarketVolatilityListSchema = z.array(MarketVolatilitySchema);

export type NewsItem = z.infer<typeof NewsItemSchema>;
export type MarketQuote = z.infer<typeof MarketQuoteSchema>;
export type MarketVolatility = z.infer<typeof MarketVolatilitySchema>;
export type Regime = z.infer<typeof RegimeSchema>;
export type VolatilityStatus = z.infer<typeof VolatilityStatusSchema>;

export interface NewsFilters {
  source?: string;
  limit?: number;
}

export const REFERENCE_NOTE = "Referência de mercado. Não é preço executável nem cotação de casa de câmbio.";

export const MARKET_SOURCE_LABEL: Record<string, string> = {
  investinglive: "Investinglive",
  infomoney: "InfoMoney",
  "agencia-brasil": "Agência Brasil",
  bcb: "Banco Central",
  mercopress: "MercoPress",
  demo: "Demonstração",
};

export const SOURCE_FILTER_OPTIONS: { value: string; label: string }[] = [
  { value: "all", label: "Todas" },
  { value: "investinglive", label: "Investinglive" },
  { value: "infomoney", label: "InfoMoney" },
  { value: "agencia-brasil", label: "Agência Brasil" },
  { value: "bcb", label: "Banco Central" },
  { value: "mercopress", label: "MercoPress" },
];
