/**
 * Telas do triangulador (U09): contratos de `/v1/market/*` lidos pelo painel (triângulos, mercado global, indicadores
 * e notícias com sentimento). Regra de rótulo: todo número sai marcado como «Executável» ou «Referência · não
 * executável». Só um triângulo com confiança `quoted` (todas as pernas com cotação firme e custo conhecido) é
 * executável; cripto, câmbio de referência, índices, macro, indicadores e sentimento são sempre `executable: false`.
 * Nada aqui envia ordem: a tela só lê e mostra.
 */
import { z } from "zod";
import { DecimalString, ModeSchema } from "./schemas";
import type { Confidence, Cycle } from "./types";

export const EXECUTABLE_LABEL = "Executável";
export const REFERENCE_LABEL = "Referência · não executável";
export const SIMULATION_NOTE = "Simulação sobre o grafo de posições. Nada é enviado nem movido: é só leitura e alerta.";

/** Triângulo executável só com confiança `quoted`; `estimated` (cotação indicativa) e `incomplete` (custo ausente) não são. */
export function triangleIsExecutable(c: Pick<Cycle, "confidence">): boolean {
  return c.confidence === "quoted";
}

export function confidenceLabel(c: Confidence): string {
  if (c === "quoted") return "cotação firme";
  if (c === "estimated") return "estimado";
  return "custo incompleto";
}

/** Moeda de um nó `moeda@local` (ex.: `BRL@casa-a` → `BRL`). */
export function currencyOfNode(node: string): string {
  const at = node.indexOf("@");
  return (at === -1 ? node : node.slice(0, at)).toUpperCase();
}

/** Local de um nó `moeda@local` (ex.: `BRL@casa-a` → `casa-a`); vazio quando o nó não tem `@`. */
export function venueOfNode(node: string): string {
  const at = node.indexOf("@");
  return at === -1 ? "" : node.slice(at + 1);
}

const NullableDecimal = DecimalString.nullable();

/** Cotação de cripto (`/v1/market/crypto`) e de macro (`/v1/market/macro`): mesma forma `MarketQuoteOut`. */
export const ReferenceQuoteSchema = z.object({
  instrument: z.string(),
  label: z.string(),
  kind: z.string(),
  source: z.string(),
  price: DecimalString,
  change_pct: NullableDecimal,
  observed_at: z.string(),
  captured_at: z.string(),
  executable: z.literal(false),
  note: z.string(),
  data_mode: ModeSchema,
});

/** Câmbio de referência (`/v1/market/references`): Frankfurter, PTAX e Open Exchange Rates. */
export const FxReferenceSchema = z.object({
  instrument: z.string(),
  source: z.string(),
  price: DecimalString,
  observed_at: z.string(),
  collected_at: z.string(),
  referencia: z.literal(true),
  executable: z.literal(false),
  note: z.string(),
  data_mode: ModeSchema,
});

export const INTERVALS = ["5m", "1d"] as const;
export type Interval = (typeof INTERVALS)[number];
export const INSTRUMENTS = ["BTC/USDT", "ETH/USDT", "USDT/BRL"] as const;
export type Instrument = (typeof INSTRUMENTS)[number];

export const INDICATOR_FIELDS = [
  ["rsi_14", "RSI (14)"],
  ["macd_line", "MACD"],
  ["macd_signal", "Sinal MACD"],
  ["macd_hist", "Histograma MACD"],
  ["stoch_k", "Estocástico %K"],
  ["stoch_d", "Estocástico %D"],
  ["adx_14", "ADX (14)"],
  ["plus_di_14", "+DI (14)"],
  ["minus_di_14", "-DI (14)"],
  ["atr_14", "ATR (14)"],
  ["natr_14", "NATR (14)"],
  ["ichimoku_tenkan", "Ichimoku Tenkan"],
  ["ichimoku_kijun", "Ichimoku Kijun"],
  ["ichimoku_senkou_a", "Ichimoku Senkou A"],
  ["ichimoku_senkou_b", "Ichimoku Senkou B"],
] as const;

export type IndicatorField = (typeof INDICATOR_FIELDS)[number][0];

const indicatorShape = Object.fromEntries(INDICATOR_FIELDS.map(([k]) => [k, NullableDecimal])) as Record<IndicatorField, typeof NullableDecimal>;

/** `/v1/market/indicators`: leitura de velas fechadas (Binance); sempre referência. */
export const IndicatorsSchema = z.object({
  instrument: z.string(),
  interval: z.enum(INTERVALS),
  status: z.enum(["ok", "insufficient_data"]),
  as_of: z.string().nullable(),
  closed_candles: z.number().int().nonnegative(),
  ...indicatorShape,
  source: z.string(),
  executable: z.literal(false),
  note: z.string(),
  data_mode: ModeSchema,
});

/** `/v1/market/sentiment`: Fear & Greed (Alternative.me), com atribuição obrigatória. */
export const SentimentSchema = z.object({
  index_id: z.string(),
  label: z.string(),
  value: z.number().int().min(0).max(100),
  classification: z.string(),
  provider: z.string(),
  observed_at: z.string(),
  captured_at: z.string(),
  attribution: z.string(),
  executable: z.literal(false),
  data_mode: ModeSchema,
});

export type ReferenceQuote = z.infer<typeof ReferenceQuoteSchema>;
export type FxReference = z.infer<typeof FxReferenceSchema>;
export type Indicators = z.infer<typeof IndicatorsSchema>;
export type Sentiment = z.infer<typeof SentimentSchema>;

export const ReferenceQuoteListSchema = ReferenceQuoteSchema.array();
export const FxReferenceListSchema = FxReferenceSchema.array();
export const SentimentListSchema = SentimentSchema.array();

/** Nome de exibição de uma série de mercado. Cripto e câmbio já vêm com `label`; índices de FRED também. */
export function referenceKindLabel(kind: string, source: string): string {
  if (source === "fred") return "Índice";
  if (kind === "crypto") return "Cripto";
  if (kind === "fx_reference") return "Câmbio";
  return "Macro";
}

/** Dígitos de exibição: preço de cripto e de câmbio mantêm casas; nunca arredonda o valor guardado. */
export function formatReferencePrice(price: string): string {
  const n = Number(price);
  if (!Number.isFinite(n)) return "—";
  const digits = Math.abs(n) >= 1000 ? 2 : Math.abs(n) >= 1 ? 4 : 6;
  return new Intl.NumberFormat("pt-BR", { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(n);
}

/** Valor com código de moeda ao lado (cripto e triângulo podem ter USDT, BTC, PYG…). */
export function formatCoinAmount(value: string | null | undefined, code: string): string {
  if (value === null || value === undefined) return "—";
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  const digits = Math.abs(n) >= 100 ? 2 : Math.abs(n) >= 1 ? 4 : 6;
  const body = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(n);
  return `${body} ${code}`;
}

export function formatPctRatio(ratio: string | null | undefined): string {
  if (ratio === null || ratio === undefined) return "—";
  const n = Number(ratio) * 100;
  if (!Number.isFinite(n)) return "—";
  const sign = n > 0 ? "+" : "";
  return `${sign}${new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(n)} %`;
}

export function formatChangePctText(pct: string | null | undefined): string {
  if (pct === null || pct === undefined) return "variação indisponível";
  const n = Number(pct);
  if (!Number.isFinite(n)) return "variação indisponível";
  const sign = n > 0 ? "+" : "";
  return `${sign}${new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(n)} %`;
}

/** Indicador em texto: `null` vira traço (nunca zero). */
export function formatIndicator(v: string | null | undefined): string {
  if (v === null || v === undefined) return "—";
  const n = Number(v);
  if (!Number.isFinite(n)) return "—";
  return new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 4 }).format(n);
}

/** Faixa do índice Fear & Greed em português, com o tom para o selo. */
export function sentimentTone(value: number): "loss" | "warn" | "neutral" | "gain" {
  if (value <= 25) return "loss";
  if (value <= 45) return "warn";
  if (value <= 55) return "neutral";
  return "gain";
}
