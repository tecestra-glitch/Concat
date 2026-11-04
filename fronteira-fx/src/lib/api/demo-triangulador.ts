/**
 * Dados de demonstração das telas do triangulador (espelho local, sem rede). Valores fixos e ilustrativos:
 * `data_mode: "demo"` em tudo, fontes com nome «demo» e atribuição que diz que é demonstração.
 */
import { DEMO_SERVER_TIME } from "./demo-data";
import { demoQuotes } from "./demo-market";
import type { FxReference, Indicators, Interval, Instrument, ReferenceQuote, Sentiment } from "./triangulador";
import type { MarketQuote } from "./market";

const base = Date.parse(DEMO_SERVER_TIME);
const at = (minutesAgo: number) => new Date(base - minutesAgo * 60_000).toISOString();

const NOTE_REF = "Referência de mercado. Não executável: nunca é preço de casa de câmbio.";

export const demoCryptoRefs: ReferenceQuote[] = demoQuotes
  .filter((q: MarketQuote) => q.kind === "crypto")
  .map((q) => ({ ...q, kind: q.kind, executable: false as const, note: NOTE_REF, data_mode: "demo" as const }));

export const demoFxRefs: FxReference[] = [
  { instrument: "USD/BRL", source: "frankfurter", price: "5.4530", observed_at: at(0), collected_at: at(0), referencia: true, executable: false, note: NOTE_REF, data_mode: "demo" },
  { instrument: "USD/PYG", source: "frankfurter", price: "5958.00", observed_at: at(0), collected_at: at(0), referencia: true, executable: false, note: NOTE_REF, data_mode: "demo" },
  { instrument: "USD/BRL", source: "ptax", price: "5.4935", observed_at: at(60), collected_at: at(0), referencia: true, executable: false, note: NOTE_REF, data_mode: "demo" },
  { instrument: "USD/BRL", source: "openexchangerates", price: "5.4611", observed_at: at(30), collected_at: at(0), referencia: true, executable: false, note: NOTE_REF, data_mode: "demo" },
];

/** Macro: séries BCB e o dólar amplo do FRED (aproximação, não é o DXY). */
export const demoMacroRefs: ReferenceQuote[] = [
  { instrument: "DTWEXBGS", label: "Dólar amplo (FRED DTWEXBGS, não é o DXY)", kind: "bcb_series", source: "fred", price: "121.6656", change_pct: "-0.12", observed_at: at(2880), captured_at: at(0), executable: false, note: NOTE_REF, data_mode: "demo" },
  ...demoQuotes
    .filter((q) => q.kind === "bcb_series")
    .map((q): ReferenceQuote => ({ ...q, executable: false, note: NOTE_REF, data_mode: "demo" })),
];

const IND_BASE: Record<Instrument, string> = { "BTC/USDT": "76006.95", "ETH/USDT": "2237.52", "USDT/BRL": "5.5179" };

export function demoIndicators(instrument: Instrument, interval: Interval): Indicators {
  const n = (x: number) => String(x);
  const price = Number(IND_BASE[instrument]);
  return {
    instrument,
    interval,
    status: "ok",
    as_of: at(interval === "5m" ? 5 : 1440),
    closed_candles: 240,
    rsi_14: n(Math.round(price % 100) / 2 + 30),
    macd_line: n(-12.5),
    macd_signal: n(-9.75),
    macd_hist: n(-2.75),
    stoch_k: n(41.2),
    stoch_d: n(38.7),
    adx_14: n(22.4),
    plus_di_14: n(18.1),
    minus_di_14: n(24.9),
    atr_14: n(412.5),
    natr_14: n(0.54),
    ichimoku_tenkan: n(75980.5),
    ichimoku_kijun: n(76340.2),
    ichimoku_senkou_a: n(76110.0),
    ichimoku_senkou_b: n(75250.4),
    source: "binance",
    executable: false,
    note: "Indicadores calculados sobre velas fechadas (shift 1). Demonstração: valores ilustrativos.",
    data_mode: "demo",
  };
}

const FNG = [
  { value: 62, classification: "Greed" },
  { value: 58, classification: "Greed" },
  { value: 47, classification: "Neutral" },
  { value: 33, classification: "Fear" },
  { value: 29, classification: "Fear" },
];

export const demoSentiment: Sentiment[] = FNG.map((f, i) => ({
  index_id: `demo-fng-${i + 1}`,
  label: "Índice Fear & Greed (demonstração)",
  value: f.value,
  classification: f.classification,
  provider: "demo",
  observed_at: at(i * 1440),
  captured_at: at(0),
  attribution: "Demonstração: valores ilustrativos, não é o índice Fear & Greed real.",
  executable: false,
  data_mode: "demo",
}));
