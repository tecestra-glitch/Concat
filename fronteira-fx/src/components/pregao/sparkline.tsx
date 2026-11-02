"use client";
import type { ReactElement } from "react";
import { pctChange } from "@/lib/pregao/derive";
import { formatPercent } from "@/lib/format";
import { cn } from "@/lib/utils";

/** Margem de 1 px em todos os lados, para o traço não ser cortado pelo viewBox. */
const PAD = 1;
const EPSILON = 1e-9;

interface Point {
  x: number;
  y: number;
}

function finiteValues(values: number[]): number[] {
  return values.filter((v) => Number.isFinite(v));
}

/** Coordenadas em pixels; vazio com menos de dois valores finitos. `max === min` → meio da altura. */
function coordinates(values: number[], width: number, height: number): Point[] {
  const v = finiteValues(values);
  const n = v.length;
  if (n < 2) return [];
  const max = v.reduce((a, b) => Math.max(a, b));
  const min = v.reduce((a, b) => Math.min(a, b));
  const span = max - min;
  return v.map((value, i) => ({
    x: PAD + (i * (width - 2 * PAD)) / (n - 1),
    y: span === 0 ? height / 2 : PAD + ((max - value) * (height - 2 * PAD)) / span,
  }));
}

function formatPoints(points: Point[]): string {
  return points.map((p) => `${p.x.toFixed(2)},${p.y.toFixed(2)}`).join(" ");
}

/** Pontos para `<polyline points>`: `"x,y x,y …"` com 2 casas; `""` com menos de dois valores. */
export function sparklinePoints(values: number[], width: number, height: number): string {
  return formatPoints(coordinates(values, width, height));
}

/** Rótulo acessível da tendência entre o primeiro e o último valor. */
export function trendLabel(values: number[]): string {
  const v = finiteValues(values);
  if (v.length < 2) return "Tendência: sem dados";
  const pct = pctChange(v[0], v[v.length - 1]);
  if (pct === null || Math.abs(pct) < EPSILON) return "Tendência: estável";
  const word = pct > 0 ? "subiu" : "caiu";
  return `Tendência: ${word} ${formatPercent(Math.abs(pct) / 100)}`;
}

export interface SparklineProps {
  values: number[];
  width?: number;
  height?: number;
  label?: string;
  className?: string;
}

/** Miniatura neutra da tendência: sem verde nem vermelho (a cor de alta/baixa fica com `Delta`). */
export function Sparkline({ values, width = 72, height = 20, label, className }: SparklineProps): ReactElement {
  const text = label ?? trendLabel(values);
  const points = coordinates(values, width, height);
  if (points.length < 2) {
    return (
      <span className="text-muted" aria-label={text}>
        —
      </span>
    );
  }
  const last = points[points.length - 1];
  return (
    <svg role="img" aria-label={text} width={width} height={height} viewBox={`0 0 ${width} ${height}`} className={cn("text-muted", className)}>
      <polyline fill="none" stroke="currentColor" strokeWidth={1.5} points={formatPoints(points)} />
      <circle cx={last.x.toFixed(2)} cy={last.y.toFixed(2)} r={2} fill="currentColor" />
    </svg>
  );
}
