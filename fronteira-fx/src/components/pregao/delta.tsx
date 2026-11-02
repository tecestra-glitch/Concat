"use client";
import type { ReactElement } from "react";
import { ArrowDown, ArrowUp, Minus } from "lucide-react";
import type { Currency } from "@/lib/api/types";
import { formatPercent, formatRate, toNumber } from "@/lib/format";
import { cn } from "@/lib/utils";

export type DeltaDirection = "up" | "down" | "flat" | "none";

export interface DeltaProps {
  /** Percentual já ×100 (`kind: "pct"`) ou valor absoluto na moeda `quote` (`kind: "abs"`). */
  value: number | string | null;
  kind?: "pct" | "abs";
  quote?: Currency;
  className?: string;
}

const FLAT_EPSILON = 1e-9;
/** U+2212, o mesmo sinal de menos de `formatPercent`. */
const MINUS = "−";

export function directionOf(value: number | null): DeltaDirection {
  if (value === null) return "none";
  if (Math.abs(value) < FLAT_EPSILON) return "flat";
  return value > 0 ? "up" : "down";
}

/**
 * Valor que seta, sinal e texto compartilham: um absoluto em PYG (derivado no cliente) é arredondado ao
 * inteiro antes de tudo (§0.10), para que "+0" com seta de alta nunca apareça.
 */
function effectiveValue(value: number | string | null, kind: "pct" | "abs", quote: Currency | undefined): number | null {
  const n = toNumber(value);
  if (n === null) return null;
  return kind === "abs" && quote === "PYG" ? Math.round(n) : n;
}

/** Texto da variação. `pct`: `formatPercent(v / 100, { sign: true })`. `abs`: sinal + `formatRate(|v|, quote)`. */
export function deltaText(value: number | string | null, kind: "pct" | "abs", quote: Currency = "USD"): string {
  const n = effectiveValue(value, kind, quote);
  if (n === null) return "—";
  if (kind === "pct") return formatPercent(n / 100, { sign: true });
  const sign = n > 0 ? "+" : n < 0 ? MINUS : "";
  return `${sign}${formatRate(Math.abs(n), quote)}`;
}

const ICON: Record<DeltaDirection, typeof ArrowUp> = { up: ArrowUp, down: ArrowDown, flat: Minus, none: Minus };
/** Sufixo de cada direção: vai no `sr-only` e, colado ao texto visível, no `title` (§10.1 item 1). */
const SR_TEXT: Record<DeltaDirection, string> = { up: " subiu", down: " caiu", flat: " estável", none: " sem variação disponível" };
const COLOR: Record<DeltaDirection, string> = { up: "text-gain", down: "text-loss", flat: "text-muted", none: "text-muted" };

/** Variação com seta, sinal e texto para leitor de tela: alta e baixa distinguíveis sem cor (§0.1 item 7). */
export function Delta({ value, kind = "pct", quote, className }: DeltaProps): ReactElement {
  const dir = directionOf(effectiveValue(value, kind, quote));
  const Icon = ICON[dir];
  const text = deltaText(value, kind, quote);
  return (
    <span
      className={cn("tnum inline-flex items-center gap-0.5", COLOR[dir], className)}
      data-testid="pregao-delta"
      data-direction={dir}
      title={`${text}${SR_TEXT[dir]}`}
    >
      <Icon size={12} aria-hidden />
      {text}
      <span className="sr-only">{SR_TEXT[dir]}</span>
    </span>
  );
}
