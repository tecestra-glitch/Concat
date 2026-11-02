"use client";
import * as React from "react";
import { createChart, createTextWatermark, LineSeries, type IChartApi, type IPriceLine, type ISeriesApi, type LineData, type UTCTimestamp, ColorType, LineStyle } from "lightweight-charts";
import type { Currency, HistoryPoint } from "@/lib/api/types";
import { formatRateFixed } from "@/components/ui/rate";
import { chartAriaLabel } from "./chart-label";

/**
 * Intraday line chart (buy/sell/mid). Uses TradingView Lightweight Charts™ (Apache-2.0); the
 * attribution logo stays on. DS16: the chart is created once per series set (module constants +
 * `series.join(",")` as dependency, so an SSE tick never recreates it); theme, locale and data
 * are applied with `applyOptions`/`setData`; colours come from the CSS tokens.
 */
export type SeriesKey = "buy" | "sell" | "mid";
export const SERIES_BUY_SELL: readonly SeriesKey[] = ["buy", "sell"];
export const SERIES_ALL: readonly SeriesKey[] = ["buy", "sell", "mid"];

const TITLE: Record<SeriesKey, string> = { buy: "Compra", sell: "Venda", mid: "Média" };
const STYLE: Record<SeriesKey, LineStyle> = { buy: LineStyle.Solid, sell: LineStyle.LargeDashed, mid: LineStyle.Dashed };

function token(name: string, fallback: string): string {
  if (typeof window === "undefined") return fallback;
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

export interface PriceChartProps {
  points: HistoryPoint[];
  height?: number;
  series?: readonly SeriesKey[];
  /** Moeda cotada: define as casas do eixo de preço. */
  quote?: Currency;
  /** Par mostrado no rótulo acessível ("USD/PYG"). */
  pair?: string;
  /** Linha pontilhada de referência (BCP, agregador) — nunca executável. */
  reference?: { value: string | number; title: string } | null;
  /** Marca d'água (modo demonstração). */
  watermark?: string | null;
}

export function PriceChart({ points, height = 220, series = SERIES_BUY_SELL, quote = "PYG", pair = "", reference = null, watermark = null }: PriceChartProps) {
  const ref = React.useRef<HTMLDivElement>(null);
  const chartRef = React.useRef<IChartApi | null>(null);
  const seriesRef = React.useRef<Partial<Record<SeriesKey, ISeriesApi<"Line">>>>({});
  const refLineRef = React.useRef<IPriceLine | null>(null);
  const seriesKey = series.join(",");

  // 1. Create once per series set (height is applied in 2, so a resize never recreates the chart).
  React.useEffect(() => {
    if (!ref.current) return;
    const chart = createChart(ref.current, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: "transparent" }, fontFamily: "var(--font-plex-mono), monospace", fontSize: 12, attributionLogo: true },
      timeScale: { timeVisible: true, secondsVisible: false },
      localization: { locale: "pt-BR" },
    });
    chartRef.current = chart;
    const map: Partial<Record<SeriesKey, ISeriesApi<"Line">>> = {};
    for (const s of seriesKey.split(",") as SeriesKey[]) {
      map[s] = chart.addSeries(LineSeries, { lineWidth: 2, title: TITLE[s], lineStyle: STYLE[s], priceLineVisible: false });
    }
    seriesRef.current = map;
    refLineRef.current = null;
    return () => {
      chart.remove();
      chartRef.current = null;
      seriesRef.current = {};
      refLineRef.current = null;
    };
  }, [seriesKey]);

  // 2. Height via applyOptions.
  React.useEffect(() => {
    chartRef.current?.applyOptions({ height });
  }, [height, seriesKey]);

  // 3. Theme: the tokens are read from <html> AFTER next-themes swaps the `.dark` class, so the
  //    trigger is the class attribute itself (a MutationObserver), never the provider's React state.
  React.useEffect(() => {
    const apply = () => {
      const chart = chartRef.current;
      if (!chart) return;
      const grid = token("--chart-grid", "#1b2440");
      const border = token("--border", "#243049");
      const surface = token("--surface", "#111827");
      chart.applyOptions({
        layout: { textColor: token("--muted", "#94a3b8") },
        grid: { vertLines: { color: grid }, horzLines: { color: grid } },
        rightPriceScale: { borderColor: border },
        timeScale: { borderColor: border },
        crosshair: { horzLine: { labelBackgroundColor: surface }, vertLine: { labelBackgroundColor: surface } },
      });
      const colors: Record<SeriesKey, string> = { buy: token("--chart-buy", "#60a5fa"), sell: token("--chart-sell", "#a9b0c0"), mid: token("--muted", "#94a3b8") };
      for (const [k, s] of Object.entries(seriesRef.current) as [SeriesKey, ISeriesApi<"Line">][]) s.applyOptions({ color: colors[k] });
    };
    apply();
    const observer = new MutationObserver(apply);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    return () => observer.disconnect();
  }, [seriesKey]);

  // 4. Price formatter follows the quoted currency.
  React.useEffect(() => {
    chartRef.current?.applyOptions({ localization: { locale: "pt-BR", priceFormatter: (p: number) => formatRateFixed(p, quote) } });
  }, [quote, seriesKey]);

  // 5. Data.
  React.useEffect(() => {
    for (const [k, s] of Object.entries(seriesRef.current) as [SeriesKey, ISeriesApi<"Line">][]) {
      const data: LineData[] = points
        .filter((p) => p[k] !== null)
        .map((p) => ({ time: Math.floor(Date.parse(p.t) / 1000) as UTCTimestamp, value: Number(p[k]) }));
      s.setData(data);
    }
    chartRef.current?.timeScale().fitContent();
  }, [points, seriesKey]);

  // 6. Reference price line (dotted, "≈ fonte").
  const refValue = reference ? Number(reference.value) : NaN;
  const refTitle = reference?.title ?? "";
  React.useEffect(() => {
    const host = seriesRef.current.buy ?? seriesRef.current.mid ?? seriesRef.current.sell;
    if (!host) return;
    if (refLineRef.current) {
      host.removePriceLine(refLineRef.current);
      refLineRef.current = null;
    }
    if (!Number.isFinite(refValue)) return;
    refLineRef.current = host.createPriceLine({ price: refValue, color: token("--muted", "#94a3b8"), lineWidth: 1, lineStyle: LineStyle.Dotted, axisLabelVisible: true, title: `≈ ${refTitle}` });
  }, [refValue, refTitle, seriesKey]);

  // 7. Demo watermark.
  React.useEffect(() => {
    const chart = chartRef.current;
    if (!chart || !watermark) return;
    const wm = createTextWatermark(chart.panes()[0], { horzAlign: "center", vertAlign: "center", lines: [{ text: watermark, color: token("--border-strong", "#64748b"), fontSize: 28, fontStyle: "bold" }] });
    return () => wm.detach();
  }, [watermark, seriesKey]);

  // <figure> + <figcaption> (não role="img"): a biblioteca põe um link de atribuição dentro do contêiner,
  // e um controle interativo dentro de role="img" é uma violação (nested-interactive).
  const label = chartAriaLabel(points, quote, pair || "Gráfico intradiário");
  return (
    <figure className="w-full" data-testid="price-chart">
      <div ref={ref} className="w-full" style={{ height }} />
      <figcaption className="sr-only">{label}</figcaption>
    </figure>
  );
}
