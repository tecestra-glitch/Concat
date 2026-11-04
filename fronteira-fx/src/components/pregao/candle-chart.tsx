"use client";
import * as React from "react";
import {
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
  LineStyle,
  createChart,
  createTextWatermark,
  type IChartApi,
  type IPriceLine,
  type ISeriesApi,
  type ITextWatermarkPluginApi,
  type Time,
} from "lightweight-charts";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import type { Currency } from "@/lib/api/types";
import { formatRate } from "@/lib/format";
import { pairOf } from "@/lib/pregao/candles";
import type { CandleSeries, ChartOverlays, IndicatorState, Timeframe } from "@/lib/pregao/types";
import { cn } from "@/lib/utils";
import {
  FALLBACK_TOKENS,
  buildCandleOptions,
  buildChartOptions,
  buildLineOptions,
  buildVolumeOptions,
  chartAriaLabel,
  chartFitKey,
  overlayLineData,
  padLeftRange,
  readChartTokens,
  toCandlestickData,
  toVolumeData,
  withChartTime,
  type ChartTokens,
} from "./candle-chart-options";

/** Linha de referência (ex.: BCP) desenhada como linha de preço; nunca executável. */
export interface ReferenceLine {
  value: string;
  label: string;
}

export interface CandleChartProps {
  series: CandleSeries | null;
  timeframe: Timeframe;
  quote: Currency;
  indicators: IndicatorState;
  /** Linhas já calculadas (F12); o gráfico não calcula nada. */
  overlays?: ChartOverlays;
  house?: string;
  reference?: ReferenceLine | null;
  demo?: boolean;
  loading?: boolean;
  error?: Error | null;
  onRetry?: () => void;
  /** Quando passado, força `style={{ height }}`; senão a altura vem do pai (`h-full`). */
  height?: number;
  className?: string;
  /** Prefixo do data-testid da figura (`${prefix}-chart`); o pregão usa "pregao", a home usa "home". */
  testIdPrefix?: string;
}

interface Handles {
  chart: IChartApi;
  candles: ISeriesApi<"Candlestick">;
  volume: ISeriesApi<"Histogram">;
  sma: ISeriesApi<"Line">;
  ema: ISeriesApi<"Line">;
  bbUpper: ISeriesApi<"Line">;
  bbLower: ISeriesApi<"Line">;
}

const WATERMARK_TEXT = "DEMONSTRAÇÃO";
const WATERMARK_SIZE = 28;

/** Valor derivado (SMA, EMA, Bollinger) em PYG é arredondado antes da exibição (§0.10). */
function formatDerived(v: number | null | undefined, quote: Currency): string {
  if (v === null || v === undefined) return "—";
  return formatRate(quote === "PYG" ? Math.round(v) : v, quote);
}

/** Título da linha de referência com o valor ("≈ BCP (referência) 5.945"): o rótulo do eixo fica desligado. */
export function referenceLineTitle(reference: ReferenceLine, quote: Currency): string {
  return `${reference.label} ${formatRate(reference.value, quote)}`;
}

/** Título em português do link do logotipo que a biblioteca põe no gráfico (a licença exige o link). */
export const ATTRIBUTION_TITLE = "Gráfico por TradingView";

function localizeAttribution(root: HTMLElement): void {
  const link = root.querySelector<HTMLAnchorElement>("a#tv-attr-logo");
  if (link && link.title !== ATTRIBUTION_TITLE) link.title = ATTRIBUTION_TITLE;
}

/** Gráfico de velas do `mid`. Cria o gráfico uma vez e atualiza séries, opções e marcas depois. */
export function CandleChart({
  series,
  timeframe,
  quote,
  indicators,
  overlays,
  house,
  reference,
  demo,
  loading = false,
  error = null,
  onRetry,
  height,
  className,
  testIdPrefix = "pregao",
}: CandleChartProps): React.ReactElement {
  const containerRef = React.useRef<HTMLDivElement>(null);
  const handlesRef = React.useRef<Handles | null>(null);
  const priceLineRef = React.useRef<IPriceLine | null>(null);
  const watermarkRef = React.useRef<ITextWatermarkPluginApi<Time> | null>(null);
  const tokensRef = React.useRef<ChartTokens>(FALLBACK_TOKENS);
  const lastFitRef = React.useRef<string | null>(null);
  const [hoverTime, setHoverTime] = React.useState<number | null>(null);
  // Intervalo dos dados na tela: durante a troca de intervalo o placeholder ainda é a série anterior
  // (keepPreviousData), e eixo, cursor e tempo dos dados seguem a série, não o botão (QA-2/QA-3).
  const dataTf = series?.tf ?? timeframe;
  // Velas já no relógio do gráfico: alimentam o `setData` e o índice do cursor (o mesmo relógio nos dois).
  const chartCandles = React.useMemo(() => withChartTime(toCandlestickData(series?.candles ?? []), dataTf), [series, dataTf]);

  // 1. Criação única do gráfico e das séries; o cleanup remove tudo.
  React.useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const chart = createChart(el, { autoSize: true });
    // A licença pede o link do logotipo, não o texto em inglês: a biblioteca recria o link quando o tema muda,
    // então o título é trocado sempre que ele (re)aparece no contêiner.
    localizeAttribution(el);
    const attribution = new MutationObserver(() => localizeAttribution(el));
    attribution.observe(el, { childList: true, subtree: true });
    const candles = chart.addSeries(CandlestickSeries, buildCandleOptions(FALLBACK_TOKENS, "PYG"));
    const volume = chart.addSeries(HistogramSeries, buildVolumeOptions(FALLBACK_TOKENS));
    chart.priceScale("volume").applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });
    const sma = chart.addSeries(LineSeries, buildLineOptions(FALLBACK_TOKENS, "sma"));
    const ema = chart.addSeries(LineSeries, buildLineOptions(FALLBACK_TOKENS, "ema"));
    const bbUpper = chart.addSeries(LineSeries, buildLineOptions(FALLBACK_TOKENS, "band"));
    const bbLower = chart.addSeries(LineSeries, buildLineOptions(FALLBACK_TOKENS, "band"));
    chart.subscribeCrosshairMove((p) => setHoverTime(p.time === undefined ? null : Number(p.time)));
    handlesRef.current = { chart, candles, volume, sma, ema, bbUpper, bbLower };
    return () => {
      attribution.disconnect();
      chart.remove();
      handlesRef.current = null;
      priceLineRef.current = null;
      watermarkRef.current = null;
    };
  }, []);

  // 2. Tema, casa de cotação e intervalo: aplica opções sem recriar nada. O next-themes troca a classe do
  //    <html> num efeito do próprio provider, que roda DEPOIS dos efeitos dos filhos; ler os tokens quando
  //    `resolvedTheme` muda pegaria os do tema anterior (QA-1). O gatilho do tema é a própria classe
  //    (MutationObserver), como em charts/price-chart.tsx; linha de referência e marca d'água vão junto.
  React.useEffect(() => {
    const apply = () => {
      const h = handlesRef.current;
      if (!h) return;
      const tokens = readChartTokens(document.documentElement);
      tokensRef.current = tokens;
      h.chart.applyOptions(buildChartOptions(tokens, { tf: dataTf, quote }));
      h.candles.applyOptions(buildCandleOptions(tokens, quote));
      h.volume.applyOptions(buildVolumeOptions(tokens));
      h.sma.applyOptions({ ...buildLineOptions(tokens, "sma"), visible: h.sma.options().visible });
      h.ema.applyOptions({ ...buildLineOptions(tokens, "ema"), visible: h.ema.options().visible });
      h.bbUpper.applyOptions({ ...buildLineOptions(tokens, "band"), visible: h.bbUpper.options().visible });
      h.bbLower.applyOptions({ ...buildLineOptions(tokens, "band"), visible: h.bbLower.options().visible });
      priceLineRef.current?.applyOptions({ color: tokens.muted });
      watermarkRef.current?.applyOptions({ lines: [{ text: WATERMARK_TEXT, color: tokens.watermark, fontSize: WATERMARK_SIZE }] });
    };
    apply();
    const observer = new MutationObserver(apply);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    return () => observer.disconnect();
  }, [quote, dataTf]);

  // 3. Dados: setData nas séries; fitContent só quando chega outra série (chave e intervalo da própria
  //    série: o placeholder do intervalo anterior não consome o enquadramento da série nova, QA-3).
  React.useEffect(() => {
    const h = handlesRef.current;
    if (!h) return;
    const candles = series?.candles ?? [];
    h.candles.setData(chartCandles);
    h.volume.setData(withChartTime(toVolumeData(candles), dataTf));
    h.sma.setData(withChartTime(overlayLineData(candles, overlays?.sma), dataTf));
    h.ema.setData(withChartTime(overlayLineData(candles, overlays?.ema), dataTf));
    h.bbUpper.setData(withChartTime(overlayLineData(candles, overlays?.bbUpper), dataTf));
    h.bbLower.setData(withChartTime(overlayLineData(candles, overlays?.bbLower), dataTf));
    const fitKey = chartFitKey(series);
    if (fitKey !== null && fitKey !== lastFitRef.current) {
      // Enquadra e acrescenta a folga à esquerda, para o primeiro rótulo do eixo não sair cortado. A última vela
      // continua na borda direita (o fim do range não muda).
      const ts = h.chart.timeScale();
      ts.fitContent();
      const range = ts.getVisibleLogicalRange();
      if (range) ts.setVisibleLogicalRange(padLeftRange(range, ts.width()));
      lastFitRef.current = fitKey;
    }
  }, [series, overlays, chartCandles, dataTf]);

  // 4. Visibilidade dos indicadores e do histograma.
  React.useEffect(() => {
    const h = handlesRef.current;
    if (!h) return;
    h.sma.applyOptions({ visible: indicators.sma });
    h.ema.applyOptions({ visible: indicators.ema });
    h.bbUpper.applyOptions({ visible: indicators.bollinger });
    h.bbLower.applyOptions({ visible: indicators.bollinger });
    h.volume.applyOptions({ visible: indicators.volume });
  }, [indicators]);

  // 5. Linha de referência (BCP/dolarPy) como linha de preço, sempre tracejada. Sem rótulo no eixo: ele cobriria
  //    as marcas da escala (5.940, 5.920) junto com o do último preço; o valor vai no título da própria linha. A
  //    biblioteca só desenha o título junto do rótulo do eixo, então nome e valor também ficam na legenda.
  React.useEffect(() => {
    const h = handlesRef.current;
    if (!h) return;
    if (priceLineRef.current) {
      h.candles.removePriceLine(priceLineRef.current);
      priceLineRef.current = null;
    }
    if (reference) {
      priceLineRef.current = h.candles.createPriceLine({
        price: Number(reference.value),
        color: tokensRef.current.muted,
        lineWidth: 1,
        lineStyle: LineStyle.LargeDashed,
        axisLabelVisible: false,
        title: referenceLineTitle(reference, quote),
      });
    }
  }, [reference, quote]);

  // 6. Marca d'água "DEMONSTRAÇÃO" no modo demo.
  React.useEffect(() => {
    const h = handlesRef.current;
    if (!h) return;
    watermarkRef.current?.detach();
    watermarkRef.current = null;
    if (demo) {
      watermarkRef.current = createTextWatermark(h.chart.panes()[0], {
        horzAlign: "center",
        vertAlign: "center",
        lines: [{ text: WATERMARK_TEXT, color: tokensRef.current.watermark, fontSize: WATERMARK_SIZE }],
      });
    }
  }, [demo]);

  const candles = series?.candles ?? [];
  const state: "loading" | "error" | "empty" | "ready" = loading
    ? "loading"
    : error
      ? "error"
      : candles.length === 0
        ? "empty"
        : "ready";

  // O cursor devolve o tempo do gráfico, então o índice usa as mesmas velas deslocadas do `setData`.
  const indexByTime = React.useMemo(() => {
    const m = new Map<number, number>();
    chartCandles.forEach((row, i) => m.set(Number(row.time), i));
    return m;
  }, [chartCandles]);

  const lastIndex = candles.length - 1;
  const lastCandle = lastIndex >= 0 ? candles[lastIndex] : null;
  const hoverIndex = hoverTime === null ? undefined : indexByTime.get(hoverTime);
  const idx = hoverIndex ?? lastIndex;
  const shown = idx >= 0 ? candles[idx] : undefined;

  const label = chartAriaLabel({
    pair: pairOf(series?.key ?? ""),
    house: house ?? "",
    tf: dataTf,
    count: candles.length,
    last: lastCandle ? lastCandle.c : null,
    quote,
  });

  const legend: { name: string; value: string; swatch: React.CSSProperties }[] = [
    {
      name: "Velas (mid)",
      value: shown ? formatRate(shown.c, quote) : "—",
      swatch: { background: "transparent", border: "1px solid var(--gain)" },
    },
  ];
  if (indicators.volume) {
    legend.push({ name: "Nº de cotações", value: shown ? String(shown.n) : "—", swatch: { background: "var(--chart-volume)" } });
  }
  if (indicators.sma) {
    legend.push({ name: "SMA 20", value: formatDerived(overlays?.sma?.[idx], quote), swatch: { background: "var(--chart-sma)" } });
  }
  if (indicators.ema) {
    legend.push({ name: "EMA 9", value: formatDerived(overlays?.ema?.[idx], quote), swatch: { background: "var(--chart-ema)" } });
  }
  if (indicators.bollinger) {
    const upper = formatDerived(overlays?.bbUpper?.[idx], quote);
    const lower = formatDerived(overlays?.bbLower?.[idx], quote);
    legend.push({ name: "Bollinger 20/2", value: `${upper} / ${lower}`, swatch: { background: "var(--chart-band)" } });
  }
  if (reference) {
    // A linha tracejada não tem rótulo no eixo: nome e valor da referência ficam aqui.
    legend.push({ name: reference.label, value: formatRate(reference.value, quote), swatch: { background: "transparent", border: "1px dashed var(--muted)" } });
  }

  // <figure> + <figcaption>, sem papel de imagem (como em charts/price-chart.tsx): a biblioteca põe um link
  // de atribuição dentro do contêiner e o estado de erro tem um botão; ambos seriam nested-interactive.
  return (
    <figure
      data-testid={`${testIdPrefix}-chart`}
      aria-label={label}
      aria-busy={state === "loading" ? true : undefined}
      data-state={state}
      data-tf={dataTf}
      data-key={series?.key ?? ""}
      data-mode={demo ? "demo" : undefined}
      className={cn("relative flex h-full min-h-[240px] flex-col", className)}
      style={height ? { height } : undefined}
    >
      <figcaption className="sr-only">{label}</figcaption>
      <div ref={containerRef} className="min-h-0 flex-1" hidden={state !== "ready"} />
      {state === "loading" ? (
        <>
          <Skeleton className="min-h-0 flex-1" />
          <span className="sr-only">Carregando…</span>
        </>
      ) : null}
      {state === "error" && error ? (
        <div role="alert" className="flex flex-1 flex-col items-start justify-center gap-2 text-sm">
          Não foi possível carregar o gráfico.
          <span className="text-muted">{error.message}</span>
          {onRetry ? (
            <Button variant="outline" size="sm" onClick={onRetry}>
              Tentar de novo
            </Button>
          ) : null}
        </div>
      ) : null}
      {state === "empty" ? (
        <div className="flex flex-1 flex-col justify-center gap-1">
          <p className="text-sm text-muted">Sem velas para este período.</p>
          <p className="text-sm text-muted">Escolha outro intervalo ou par.</p>
        </div>
      ) : null}
      {state === "ready" ? (
        <ul aria-label="Séries do gráfico" className="flex flex-wrap gap-3 px-1 py-1 text-xs">
          {legend.map((item) => (
            <li key={item.name} className="flex items-center gap-1.5">
              <span aria-hidden="true" className="inline-block size-2 shrink-0 rounded-sm" style={item.swatch} />
              <span className="text-muted">{item.name}</span>
              <span className="tnum text-foreground">{item.value}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </figure>
  );
}
