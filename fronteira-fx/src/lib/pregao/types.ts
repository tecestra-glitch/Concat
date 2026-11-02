import type { Channel, City, Currency, DataMode, QuoteKind } from "@/lib/api/types";

export type Timeframe = "15m" | "1h" | "4h" | "1d";
export const TIMEFRAMES: readonly Timeframe[] = ["15m", "1h", "4h", "1d"];
export const TF_SECONDS: Record<Timeframe, number> = { "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400 };
export const TIMEFRAME_LABEL: Record<Timeframe, string> = { "15m": "15 min", "1h": "1 hora", "4h": "4 horas", "1d": "1 dia" };

export type PairKey = "USD/PYG" | "BRL/PYG" | "USD/BRL";
export const PAIRS: readonly PairKey[] = ["USD/PYG", "BRL/PYG", "USD/BRL"];
export const PAIR_LABEL: Record<PairKey, string> = { "USD/PYG": "USD/PYG", "BRL/PYG": "BRL/PYG", "USD/BRL": "USD/BRL" };

export type SeriesKey = string;
export type SessionStatus = "open" | "closed" | "pre" | "unknown";
export type HouseChannel = "physical" | "digital";
export type HouseCity = Exclude<City, null>;

export interface Candle {
  t: string;
  o: string;
  h: string;
  l: string;
  c: string;
  n: number;
  spread_avg: string | null;
  buy_c: string | null;
  sell_c: string | null;
  data_mode: DataMode;
}

export interface CandleSeries {
  key: string;
  tf: Timeframe;
  candles: Candle[];
  data_mode: DataMode;
}

export interface SessionStats {
  key: string;
  day_start: string;
  open: string | null;
  high: string | null;
  low: string | null;
  last: string | null;
  last_at: string | null;
  change_abs: string | null;
  change_pct: string | null;
  n_quotes: number;
  spread_avg: string | null;
  houses: number;
  data_mode: DataMode;
}

export interface HouseHours {
  name?: string | null;
  city?: HouseCity | null;
  channel?: HouseChannel;
  tz: string;
  days: number[];
  opens: string;
  closes: string;
}

export interface HouseSession {
  source_id: string;
  name: string;
  city: HouseCity | null;
  tz: string | null;
  channel: HouseChannel | null;
  reference: boolean;
  status: SessionStatus;
  opens_at: string | null;
  closes_at: string | null;
  next_change_at: string | null;
  data_mode: DataMode;
}

export const STATUS_LABEL: Record<SessionStatus, string> = {
  open: "aberta",
  closed: "fechada",
  pre: "pré-abertura",
  unknown: "sem horário",
};
export const STATUS_BADGE: Record<SessionStatus, "gain" | "outline" | "warn"> = {
  open: "gain",
  closed: "outline",
  pre: "warn",
  unknown: "outline",
};

export interface IndicatorState {
  sma: boolean;
  ema: boolean;
  bollinger: boolean;
  volume: boolean;
}
export const INDICATOR_DEFAULTS: IndicatorState = { sma: false, ema: false, bollinger: false, volume: true };
export const INDICATOR_PERIODS = { sma: 20, ema: 9, bollinger: { period: 20, k: 2 } } as const;

/** Série alinhada às velas; `null` onde o indicador ainda não existe. */
export type Series = (number | null)[];
/** Linhas já calculadas (F12) que o gráfico (F3) desenha; chave ausente = indicador desligado. */
export interface ChartOverlays {
  sma?: Series;
  ema?: Series;
  bbUpper?: Series;
  bbLower?: Series;
}

/** Linha da fita: última cotação de uma série. */
export interface TickerItem {
  key: SeriesKey;
  pair: PairKey;
  source_id: string;
  house: string;
  city: City;
  kind: QuoteKind;
  buy: string | null;
  sell: string | null;
  mid: number | null;
  change_pct: number | null;
  captured_at: string;
  incomplete: boolean;
  data_mode: DataMode;
}

/** Uma casa (ou referência) em um par: alimenta livro, lista e mapa de calor. */
export interface BookLevel {
  key: SeriesKey;
  pair: PairKey;
  source_id: string;
  house: string;
  city: City;
  /** Canal da cotação (`aggregator` = dolarPy, sempre referência). */
  channel: Channel;
  kind: QuoteKind;
  buy: string | null;
  sell: string | null;
  spread_pct: number | null;
  agio_buy_pct: number | null;
  agio_sell_pct: number | null;
  status: SessionStatus;
  incomplete: boolean;
  captured_at: string;
  data_mode: DataMode;
}

/** Linha de "Últimas atualizações": uma cotação publicada. */
export interface Print {
  id: string;
  key: SeriesKey;
  pair: PairKey;
  source_id: string;
  house: string;
  city: City;
  kind: QuoteKind;
  buy: string | null;
  sell: string | null;
  mid: number | null;
  prev_mid: number | null;
  change_pct: number | null;
  captured_at: string;
  incomplete: boolean;
  data_mode: DataMode;
}

/** Linha da lista: nível do livro + variação do dia + miniatura. */
export interface WatchlistRow extends BookLevel {
  change_pct: number | null;
  spark: number[];
}

/** Célula do mapa de calor de spread. */
export interface HeatCell {
  key: SeriesKey;
  pair: PairKey;
  source_id: string;
  house: string;
  spread_pct: number | null;
  status: SessionStatus;
  captured_at: string;
}

export type { Currency };
