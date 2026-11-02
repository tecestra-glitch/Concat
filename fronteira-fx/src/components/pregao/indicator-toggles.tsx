"use client";
import type { KeyboardEvent, ReactElement } from "react";
import { rovingIndex } from "@/components/pregao/timeframe-bar";
import type { IndicatorState } from "@/lib/pregao/types";
import { cn } from "@/lib/utils";

export const INDICATOR_ITEMS: readonly { id: keyof IndicatorState; label: string; title: string }[] = [
  { id: "sma", label: "SMA 20", title: "Média simples de 20 velas" },
  { id: "ema", label: "EMA 9", title: "Média exponencial de 9 velas" },
  { id: "bollinger", label: "Bollinger", title: "Bandas de Bollinger (20, 2σ)" },
  { id: "volume", label: "Nº de cotações", title: "Nº de cotações por vela" },
];

export interface IndicatorTogglesProps {
  value: IndicatorState;
  onChange: (next: IndicatorState) => void;
  disabled?: boolean;
  className?: string;
}

/**
 * Alternáveis de indicadores. Setas só movem o foco (roving tabindex lido do DOM);
 * Espaço e Enter alternam pelo clique nativo do botão.
 */
export function IndicatorToggles({ value, onChange, disabled = false, className }: IndicatorTogglesProps): ReactElement {
  function onKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    const buttons = Array.from(e.currentTarget.querySelectorAll<HTMLButtonElement>("button"));
    const current = Math.max(0, buttons.indexOf(e.target as HTMLButtonElement));
    const idx = rovingIndex(current, e.key, buttons.length);
    if (idx === null) return;
    e.preventDefault();
    buttons.forEach((b, j) => {
      b.tabIndex = j === idx ? 0 : -1;
    });
    buttons[idx].focus();
  }

  return (
    <div
      role="toolbar"
      aria-label="Indicadores"
      data-testid="pregao-indicators"
      onKeyDown={onKeyDown}
      className={cn("inline-flex flex-wrap items-center gap-1", className)}
    >
      {INDICATOR_ITEMS.map(({ id, label, title }, i) => {
        const pressed = value[id];
        return (
          <button
            key={id}
            type="button"
            aria-pressed={pressed}
            data-indicator={id}
            title={title}
            tabIndex={i === 0 ? 0 : -1}
            disabled={disabled}
            onClick={() => onChange({ ...value, [id]: !value[id] })}
            className={cn(
              "h-8 max-sm:h-10 rounded-sm border border-border px-2.5 text-[13px] transition-colors",
              "focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2",
              "disabled:pointer-events-none disabled:opacity-50",
              pressed ? "bg-surface-2 text-foreground" : "text-muted hover:text-foreground",
            )}
          >
            {label}
          </button>
        );
      })}
    </div>
  );
}
