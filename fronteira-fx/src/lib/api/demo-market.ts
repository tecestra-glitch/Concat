/**
 * Dados de demonstração do módulo market (espelho do `market/demo.py` do backend, sem rede).
 * Manchetes ilustrativas com fonte "demo" e links `.invalid`: nunca parecem notícias reais.
 * Os valores são fixos; só os horários acompanham o relógio da demonstração.
 */
import { DEMO_SERVER_TIME } from "./demo-data";
import type { MarketQuote, MarketVolatility, NewsFilters, NewsItem } from "./market";

const base = Date.parse(DEMO_SERVER_TIME);
const at = (minutesAgo: number) => new Date(base - minutesAgo * 60_000).toISOString();

const HEADLINES: { title: string; minutesAgo: number }[] = [
  { title: "Demonstração: manchete ilustrativa sobre a decisão da Selic", minutesAgo: 60 },
  { title: "Demonstração: manchete ilustrativa sobre o dólar fechando em alta", minutesAgo: 140 },
  { title: "Demonstração: manchete ilustrativa sobre a ata do Copom", minutesAgo: 300 },
  { title: "Demonstração: manchete ilustrativa sobre o guarani", minutesAgo: 480 },
  { title: "Demonstração: manchete ilustrativa sobre cripto e volatilidade", minutesAgo: 720 },
  { title: "Demonstração: manchete ilustrativa sobre câmbio na fronteira", minutesAgo: 960 },
];

export const demoNews: NewsItem[] = HEADLINES.map((h, i) => ({
  id: `demo-news-${i + 1}`,
  source: "demo",
  feed: "demo-ilustrativo",
  title: h.title,
  link: `https://demo.invalid/manchete/${i + 1}`,
  excerpt: null,
  attribution: "Dados ilustrativos (demonstração), não são notícias reais.",
  published_at: at(h.minutesAgo),
  captured_at: at(0),
  data_mode: "demo",
}));

export function demoNewsList(f: NewsFilters = {}): NewsItem[] {
  const limit = f.limit ?? 50;
  const rows = f.source && f.source !== "all" ? demoNews.filter((n) => n.source === f.source) : demoNews;
  return rows.slice(0, limit);
}

export const demoQuotes: MarketQuote[] = [
  { instrument: "BTC/USDT", label: "Bitcoin em USDT", kind: "crypto", source: "demo", price: "76006.95", change_pct: "-1.18", observed_at: at(0), captured_at: at(0), executable: false, note: "Referência de mercado. Não é preço executável nem cotação de casa de câmbio.", data_mode: "demo" },
  { instrument: "ETH/USDT", label: "Ethereum em USDT", kind: "crypto", source: "demo", price: "2237.52", change_pct: "-0.73", observed_at: at(0), captured_at: at(0), executable: false, note: "Referência de mercado. Não é preço executável nem cotação de casa de câmbio.", data_mode: "demo" },
  { instrument: "USDT/BRL", label: "Dólar cripto (USDT em reais)", kind: "crypto", source: "demo", price: "5.5179", change_pct: "0.88", observed_at: at(0), captured_at: at(0), executable: false, note: "Referência de mercado. Não é preço executável nem cotação de casa de câmbio.", data_mode: "demo" },
  { instrument: "USD/BRL", label: "USD/BRL (BCE via Frankfurter)", kind: "fx_reference", source: "demo", price: "5.453", change_pct: null, observed_at: at(0), captured_at: at(0), executable: false, note: "Referência de mercado. Não é preço executável nem cotação de casa de câmbio.", data_mode: "demo" },
  { instrument: "USD/PYG", label: "USD/PYG (guarani, via Frankfurter)", kind: "fx_reference", source: "demo", price: "5958", change_pct: null, observed_at: at(0), captured_at: at(0), executable: false, note: "Referência de mercado. Não é preço executável nem cotação de casa de câmbio.", data_mode: "demo" },
  { instrument: "PTAX venda", label: "PTAX venda (SGS 1)", kind: "bcb_series", source: "demo", price: "5.4935", change_pct: "1.33", observed_at: at(0), captured_at: at(0), executable: false, note: "Referência de mercado. Não é preço executável nem cotação de casa de câmbio.", data_mode: "demo" },
  { instrument: "Selic meta", label: "Taxa Selic meta, % a.a. (SGS 432)", kind: "bcb_series", source: "demo", price: "13.75", change_pct: null, observed_at: at(0), captured_at: at(0), executable: false, note: "Referência de mercado. Não é preço executável nem cotação de casa de câmbio.", data_mode: "demo" },
];

const vol = (
  instrument: string,
  regime: MarketVolatility["regime"],
  extra: Partial<MarketVolatility> = {},
): MarketVolatility => ({
  instrument,
  status: "ok",
  as_of: at(0),
  last_close: null,
  last_move_pct: "0.12",
  ewma_pct_5m: "0.08",
  parkinson_1d_pct: "0.41",
  parkinson_20d_pct: "0.37",
  ratio_1d_20d: "1.11",
  atr_14_5m: "0.02",
  regime,
  alert: false,
  reasons: [],
  data_mode: "demo",
  ...extra,
});

export const demoVolatility: MarketVolatility[] = [
  vol("BTC/USDT", "normal", { last_move_pct: "-0.31", ewma_pct_5m: "0.18", parkinson_1d_pct: "1.62", parkinson_20d_pct: "1.48", ratio_1d_20d: "1.09", atr_14_5m: "412.5" }),
  vol("ETH/USDT", "alta", { last_move_pct: "-0.74", ewma_pct_5m: "0.22", parkinson_1d_pct: "2.15", parkinson_20d_pct: "1.66", ratio_1d_20d: "1.62", atr_14_5m: "9.8" }),
  vol("USDT/BRL", "normal", { last_move_pct: "0.12", ewma_pct_5m: "0.05", parkinson_1d_pct: "0.41", parkinson_20d_pct: "0.37", ratio_1d_20d: "1.11", atr_14_5m: "0.0061" }),
];
