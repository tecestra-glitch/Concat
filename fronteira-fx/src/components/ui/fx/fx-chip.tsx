/**
 * Chip de estado (4 tons). Elemento Uiverse «chip-estado» (kamehame-ha), MIT, Uiverse.io. Reescrito com os tokens
 * do app; sem CSS copiado. Ver `docs/creditos-uiverse.md` e `credits.ts`.
 */
import * as React from "react";
import { cn } from "@/lib/utils";

export type FxChipTone = "accent" | "warn" | "gain" | "loss" | "demo" | "neutral";

const TONE_VAR: Record<FxChipTone, string> = {
  accent: "var(--accent)",
  warn: "var(--warn)",
  gain: "var(--gain)",
  loss: "var(--loss)",
  demo: "var(--demo)",
  neutral: "var(--muted)",
};

/** Texto sempre em --foreground (≥ 4,5:1 sobre o matiz a 14 %); o matiz vai na borda, no fundo e no ponto. */
export function FxChip({ tone = "neutral", children, className, ...props }: React.HTMLAttributes<HTMLSpanElement> & { tone?: FxChipTone }) {
  return (
    <span
      className={cn("inline-flex h-6 items-center gap-1.5 whitespace-nowrap rounded-chip border px-2 text-caption font-medium text-foreground", className)}
      style={{
        borderColor: TONE_VAR[tone],
        backgroundColor: `color-mix(in oklab, ${TONE_VAR[tone]} 14%, transparent)`,
      }}
      {...props}
    >
      <span aria-hidden className="size-1.5 rounded-full" style={{ backgroundColor: TONE_VAR[tone] }} />
      {children}
    </span>
  );
}
