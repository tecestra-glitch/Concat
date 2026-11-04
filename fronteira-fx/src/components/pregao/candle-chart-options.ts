/**
 * Opções e dados do gráfico de velas (F3). Arquivo puro: sem React e sem DOM obrigatório.
 * As cores vêm dos tokens CSS (§0.13); `FALLBACK_TOKENS` usa rgb()/rgba() (D42), nunca #hex.
 */
import {
  ColorType,
  LineStyle,
  TickMarkType,
  type CandlestickData,
  type CandlestickSeriesPartialOptions,
  type ChartOptions,
  type DeepPartial,
  type HistogramData,
  type HistogramSeriesPartialOptions,
  type LineData,
  type LineSeriesPartialOptions,
  type Time,
  type UTCTimestamp,
  type WhitespaceData,
} from "lightweight-charts";
import type { Currency } from "@/lib/api/types";
import { formatRate } from "@/lib/format";
import { TIMEFRAME_LABEL, type Candle, type CandleSeries, type Series, type Timeframe } from "@/lib/pregao/types";

export interface ChartTokens {
  surface: string;
  grid: string;
  muted: string;
  foreground: string;
  border: string;
  gain: string;
  loss: string;
  volume: string;
  sma: string;
  ema: string;
  band: string;
  watermark: string;
  fontMono: string;
}

/** Nome da variável CSS de cada token (§0.13). */
export const TOKEN_VARS: Record<keyof ChartTokens, string> = {
  surface: "--surface",
  grid: "--chart-grid",
  muted: "--muted",
  foreground: "--foreground",
  border: "--border",
  gain: "--gain",
  loss: "--loss",
  volume: "--chart-volume",
  sma: "--chart-sma",
  ema: "--chart-ema",
  band: "--chart-band",
  watermark: "--chart-watermark",
  fontMono: "--font-mono",
};

/** Valores do tema claro em rgb(); usados só quando a variável CSS vem vazia (ex.: testes em Node). */
export const FALLBACK_TOKENS: ChartTokens = {
  surface: "rgb(255 255 255)",
  grid: "rgb(229 233 242)",
  muted: "rgb(91 100 120)",
  foreground: "rgb(11 16 32)",
  border: "rgb(217 222 234)",
  gain: "rgb(4 120 87)",
  loss: "rgb(190 18 60)",
  volume: "rgb(199 210 254)",
  sma: "rgb(37 99 235)",
  ema: "rgb(124 58 237)",
  band: "rgb(100 116 139)",
  watermark: "rgba(11, 16, 32, 0.08)",
  fontMono: "ui-monospace, Menlo, monospace",
};

/** Monta os tokens a partir de uma função que lê a variável CSS; valor vazio cai no fallback do próprio token. */
export function tokensFromGetter(get: (cssVar: string) => string): ChartTokens {
  const out = {} as ChartTokens;
  for (const key of Object.keys(TOKEN_VARS) as (keyof ChartTokens)[]) {
    out[key] = get(TOKEN_VARS[key]) || FALLBACK_TOKENS[key];
  }
  return out;
}

export function readChartTokens(root: HTMLElement): ChartTokens {
  const style = getComputedStyle(root);
  return tokensFromGetter((v) => style.getPropertyValue(v).trim());
}

type TickKind = "time" | "day" | "month" | "year";

function tickKind(type: TickMarkType): TickKind {
  switch (type) {
    case TickMarkType.Year:
      return "year";
    case TickMarkType.Month:
      return "month";
    case TickMarkType.DayOfMonth:
      return "day";
    default:
      return "time";
  }
}

const TZ = "America/Asuncion";

/*
 * Relógio do gráfico (QA-2). O lightweight-charts decide o tipo de cada marca (hora, dia, mês, ano) pela
 * data em UTC do tempo que recebe. Por isso o tempo entregue a ele já é o relógio de exibição, e toda
 * formatação é em UTC desse tempo:
 * - `1d`: o bucket é o dia UTC (§0.4), então o tempo não é deslocado e a vela de 02/11 00:00Z é "02/11";
 * - intradiários: o tempo é deslocado pelo fuso de Assunção (guia de fusos do lightweight-charts), então as
 *   horas saem no relógio local e a marca de troca de dia cai na meia-noite de Assunção, com a data nova.
 */
const asuncionParts = new Intl.DateTimeFormat("en-US", {
  timeZone: TZ,
  hourCycle: "h23",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
});

/** Diferença (s) entre o relógio de Assunção e o UTC no instante `timeSec` (−10800 com UTC−3). */
function asuncionOffsetSec(timeSec: number): number {
  const p: Record<string, number> = {};
  for (const part of asuncionParts.formatToParts(new Date(timeSec * 1000))) {
    if (part.type !== "literal") p[part.type] = Number(part.value);
  }
  const local = Date.UTC(p.year, p.month - 1, p.day, p.hour, p.minute, p.second) / 1000;
  return local - Math.floor(timeSec);
}

/**
 * Desloca linhas de dados (velas, histograma, indicadores) para o relógio do gráfico. Um único deslocamento
 * por série, o da última linha: numa troca de fuso (um navegador com tzdata antigo ainda vê horário de verão
 * em Assunção) um deslocamento por vela repetiria horas locais, e o gráfico recusa tempos fora de ordem.
 * As linhas de uma série têm todas os mesmos tempos, então velas, histograma e linhas recebem o mesmo valor.
 */
export function withChartTime<T extends { time: UTCTimestamp }>(rows: T[], tf: Timeframe): T[] {
  if (tf === "1d" || rows.length === 0) return rows;
  const offset = asuncionOffsetSec(rows[rows.length - 1].time);
  return rows.map((r) => ({ ...r, time: (r.time + offset) as UTCTimestamp }));
}

type LabelKind = TickKind | "cursorDay" | "cursorTime";
const LABEL_FORMAT: Record<LabelKind, Intl.DateTimeFormatOptions> = {
  time: { hour: "2-digit", minute: "2-digit" },
  day: { day: "2-digit", month: "2-digit" },
  month: { month: "short" },
  year: { year: "numeric" },
  cursorDay: { day: "2-digit", month: "2-digit", year: "numeric" },
  cursorTime: { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" },
};
const labelFormatters = new Map<LabelKind, Intl.DateTimeFormat>();

function formatLabel(chartSec: number, kind: LabelKind): string {
  let fmt = labelFormatters.get(kind);
  if (!fmt) {
    fmt = new Intl.DateTimeFormat("pt-BR", { timeZone: "UTC", hourCycle: "h23", ...LABEL_FORMAT[kind] });
    labelFormatters.set(kind, fmt);
  }
  return fmt.format(new Date(chartSec * 1000)).replace(",", "");
}

/** Rótulo do eixo para um tempo do gráfico (`withChartTime`), em pt-BR. */
export function formatTick(chartSec: number, kind: TickKind): string {
  return formatLabel(chartSec, kind);
}

/** Rótulo do cursor: data no `1d` (dia UTC do bucket); data e hora locais nos intradiários. */
export function formatCursor(chartSec: number, tf: Timeframe): string {
  return formatLabel(chartSec, tf === "1d" ? "cursorDay" : "cursorTime");
}

export function buildChartOptions(t: ChartTokens, opts: { tf: Timeframe; quote: Currency }): DeepPartial<ChartOptions> {
  const { tf, quote } = opts;
  return {
    autoSize: true,
    layout: {
      background: { type: ColorType.Solid, color: t.surface },
      textColor: t.muted,
      fontSize: 12,
      fontFamily: t.fontMono,
      attributionLogo: true,
    },
    grid: { vertLines: { color: t.grid }, horzLines: { color: t.grid } },
    rightPriceScale: { borderColor: t.border },
    timeScale: {
      borderColor: t.border,
      timeVisible: tf !== "1d",
      secondsVisible: false,
      shiftVisibleRangeOnNewBar: false,
      tickMarkFormatter: (time: Time, type: TickMarkType) => formatTick(Number(time), tickKind(type)),
    },
    crosshair: {
      horzLine: { labelBackgroundColor: t.surface },
      vertLine: { labelBackgroundColor: t.surface },
    },
    localization: {
      locale: "pt-BR",
      priceFormatter: (p: number) => formatRate(String(p), quote),
      timeFormatter: (time: Time) => formatCursor(Number(time), tf),
    },
  };
}

/** Velas: alta com corpo vazado e borda verde; baixa com corpo cheio em vermelho (distinguíveis também pela forma). */
export function buildCandleOptions(t: ChartTokens, quote: Currency): CandlestickSeriesPartialOptions {
  return {
    upColor: "rgba(0,0,0,0)",
    downColor: t.loss,
    borderVisible: true,
    borderUpColor: t.gain,
    borderDownColor: t.loss,
    wickUpColor: t.gain,
    wickDownColor: t.loss,
    priceLineVisible: false,
    lastValueVisible: true,
    priceFormat: {
      type: "custom",
      minMove: quote === "PYG" ? 1 : 0.0001,
      formatter: (p: number) => formatRate(String(p), quote),
    },
  };
}

export function buildVolumeOptions(t: ChartTokens): HistogramSeriesPartialOptions {
  return {
    color: t.volume,
    priceFormat: { type: "volume" },
    priceScaleId: "volume",
    priceLineVisible: false,
    lastValueVisible: false,
  };
}

export function buildLineOptions(t: ChartTokens, which: "sma" | "ema" | "band"): LineSeriesPartialOptions {
  if (which === "band") {
    return { color: t.band, lineWidth: 1, lineStyle: LineStyle.Dashed, priceLineVisible: false, lastValueVisible: false, visible: false };
  }
  return {
    color: which === "sma" ? t.sma : t.ema,
    lineWidth: 2,
    priceLineVisible: false,
    lastValueVisible: false,
    visible: false,
  };
}

/**
 * Folga à esquerda (px) antes da primeira vela. O rótulo do eixo é centrado na vela: sem a folga, a primeira marca
 * (ex.: "22/10") sai pela borda do canvas e fica "2/10" (390 e 1024 px). A folga é de espaço vazio, sem esconder velas.
 */
export const LEFT_EDGE_PAD_PX = 28;

/**
 * Range lógico com a folga à esquerda: a primeira vela (`range.from`) fica a `padPx` da borda, e a última (`range.to`)
 * continua na borda direita. Como o range fica mais largo, as velas encolhem: a folga em bars sai de
 * `pad × L / (largura − pad)`, com L = bars de dados (a equação que deixa a folga em px exata).
 */
export function padLeftRange(range: { from: number; to: number }, widthPx: number, padPx: number = LEFT_EDGE_PAD_PX): { from: number; to: number } {
  const data = range.to - range.from;
  if (!(data > 0) || !(widthPx > padPx)) return range;
  const bars = (padPx * data) / (widthPx - padPx);
  return { from: range.from - bars, to: range.to };
}

/** Chave de enquadramento (`fitContent`): a da própria série, para valer só quando chega o intervalo pedido. */
export function chartFitKey(series: CandleSeries | null): string | null {
  return series && series.candles.length > 0 ? `${series.key}|${series.tf}` : null;
}

export function toCandlestickData(candles: Candle[]): CandlestickData<UTCTimestamp>[] {
  return candles.map((c) => ({
    time: Math.floor(Date.parse(c.t) / 1000) as UTCTimestamp,
    open: Number(c.o),
    high: Number(c.h),
    low: Number(c.l),
    close: Number(c.c),
  }));
}

/** Histograma do número de cotações por vela (rótulo visível: "Nº de cotações"). */
export function toVolumeData(candles: Candle[]): HistogramData<UTCTimestamp>[] {
  return candles.map((c) => ({ time: Math.floor(Date.parse(c.t) / 1000) as UTCTimestamp, value: c.n }));
}

/** Linha alinhada às velas; `null` vira ponto em branco (sem valor). */
export function toLineData(candles: Candle[], values: Series): (LineData<UTCTimestamp> | WhitespaceData<UTCTimestamp>)[] {
  if (values.length !== candles.length) {
    throw new RangeError("a série de valores precisa ter o mesmo tamanho das velas");
  }
  return candles.map((c, i) => {
    const time = Math.floor(Date.parse(c.t) / 1000) as UTCTimestamp;
    const v = values[i];
    return v === null ? { time } : { time, value: v };
  });
}

/**
 * Linha de overlay para o gráfico: sem valores, ou com extensão diferente das velas, devolve `[]`
 * (a linha some em vez de derrubar a árvore React). `toLineData` continua estrito.
 */
export function overlayLineData(candles: Candle[], values: Series | undefined): (LineData<UTCTimestamp> | WhitespaceData<UTCTimestamp>)[] {
  if (!values || values.length !== candles.length) return [];
  return toLineData(candles, values);
}

export function chartAriaLabel(a: {
  pair: string;
  house: string;
  tf: Timeframe;
  count: number;
  last: string | null;
  quote: Currency;
}): string {
  if (a.count === 0) return "Gráfico de velas sem dados";
  const housePart = a.house ? `, ${a.house}` : "";
  return `Gráfico de velas ${a.pair}${housePart}, intervalo ${TIMEFRAME_LABEL[a.tf]}, ${a.count} velas, último ${formatRate(a.last, a.quote)}`;
}
