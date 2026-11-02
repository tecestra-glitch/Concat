"use client";
import * as React from "react";
import { createChart, LineSeries, type IChartApi, type ISeriesApi, type LineData, type UTCTimestamp, ColorType, LineStyle } from "lightweight-charts";
import { useTheme } from "next-themes";
import type { HistoryPoint } from "@/lib/api/types";

/**
 * Intraday line chart (buy/sell/mid). Uses TradingView Lightweight Charts™
 * (Apache-2.0) — attribution preserved via the library's built-in logo.
 */
export function PriceChart({ points, height = 220, series = ["buy", "sell"] }: { points: HistoryPoint[]; height?: number; series?: ("buy" | "sell" | "mid")[] }) {
  const ref = React.useRef<HTMLDivElement>(null);
  const chartRef = React.useRef<IChartApi | null>(null);
  const seriesRef = React.useRef<Record<string, ISeriesApi<"Line">>>({});
  const { resolvedTheme } = useTheme();
  const dark = resolvedTheme !== "light";

  React.useEffect(() => {
    if (!ref.current) return;
    const chart = createChart(ref.current, {
      height,
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: "transparent" }, textColor: dark ? "#94a3b8" : "#5b6478", fontFamily: "var(--font-plex-mono), monospace", fontSize: 11, attributionLogo: true },
      grid: { vertLines: { color: dark ? "#1b2440" : "#e6eaf3" }, horzLines: { color: dark ? "#1b2440" : "#e6eaf3" } },
      rightPriceScale: { borderColor: dark ? "#243049" : "#d9deea" },
      timeScale: { borderColor: dark ? "#243049" : "#d9deea", timeVisible: true, secondsVisible: false },
      crosshair: { horzLine: { labelBackgroundColor: dark ? "#111827" : "#ffffff" }, vertLine: { labelBackgroundColor: dark ? "#111827" : "#ffffff" } },
      localization: { locale: "pt-BR" },
    });
    chartRef.current = chart;
    const colors: Record<string, string> = { buy: dark ? "#34d399" : "#059669", sell: dark ? "#fb7185" : "#e11d48", mid: dark ? "#60a5fa" : "#2563eb" };
    for (const s of series) {
      seriesRef.current[s] = chart.addSeries(LineSeries, { color: colors[s], lineWidth: 2, title: s === "buy" ? "Compra" : s === "sell" ? "Venda" : "Média", lineStyle: s === "mid" ? LineStyle.Dashed : LineStyle.Solid, priceLineVisible: false });
    }
    return () => {
      chart.remove();
      chartRef.current = null;
      seriesRef.current = {};
    };
  }, [dark, height, series]);

  React.useEffect(() => {
    for (const s of series) {
      const data: LineData[] = points
        .filter((p) => p[s] !== null)
        .map((p) => ({ time: Math.floor(Date.parse(p.t) / 1000) as UTCTimestamp, value: Number(p[s]) }));
      seriesRef.current[s]?.setData(data);
    }
    chartRef.current?.timeScale().fitContent();
  }, [points, series]);

  return <div ref={ref} role="img" aria-label="Gráfico intradiário de compra e venda" className="w-full" style={{ height }} />;
}
