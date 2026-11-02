"use client";
import type { KeyboardEvent, ReactElement } from "react";
import { TIMEFRAMES, TIMEFRAME_LABEL, type Timeframe } from "@/lib/pregao/types";
import { cn } from "@/lib/utils";

/**
 * Próximo índice de um grupo com foco ordenado (roving tabindex).
 * ArrowRight/ArrowDown avançam em ciclo; ArrowLeft/ArrowUp recuam; Home vai ao primeiro; End ao último.
 * Qualquer outra tecla devolve `null`.
 */
export function rovingIndex(current: number, key: string, length: number): number | null {
  if (length <= 0) return null;
  switch (key) {
    case "ArrowRight":
    case "ArrowDown":
      return (current + 1) % length;
    case "ArrowLeft":
    case "ArrowUp":
      return (current - 1 + length) % length;
    case "Home":
      return 0;
    case "End":
      return length - 1;
    default:
      return null;
  }
}

export interface TimeframeBarProps {
  value: Timeframe;
  onChange: (tf: Timeframe) => void;
  disabled?: boolean;
  className?: string;
}

/** Seletor de intervalo das velas (15m, 1h, 4h, 1d). Atalhos 1–4 ficam na F17. */
export function TimeframeBar({ value, onChange, disabled = false, className }: TimeframeBarProps): ReactElement {
  const current = Math.max(0, TIMEFRAMES.indexOf(value));

  function onKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    if (disabled) return;
    const idx = rovingIndex(current, e.key, TIMEFRAMES.length);
    if (idx === null) return;
    e.preventDefault();
    onChange(TIMEFRAMES[idx]);
    e.currentTarget.querySelectorAll<HTMLElement>('[role="radio"]')[idx].focus();
  }

  return (
    <div
      role="radiogroup"
      aria-label="Intervalo das velas"
      data-testid="pregao-timeframe"
      onKeyDown={onKeyDown}
      className={cn("inline-flex rounded-md border border-border bg-surface p-0.5", className)}
    >
      {TIMEFRAMES.map((tf, i) => {
        const checked = tf === value;
        return (
          <button
            key={tf}
            type="button"
            role="radio"
            aria-checked={checked}
            data-tf={tf}
            tabIndex={checked ? 0 : -1}
            aria-label={`${TIMEFRAME_LABEL[tf]} (tecla ${i + 1})`}
            disabled={disabled}
            onClick={() => onChange(tf)}
            className={cn(
              "tnum h-8 max-sm:h-10 min-w-10 rounded-sm px-2.5 text-[13px] transition-colors",
              "focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2",
              "disabled:pointer-events-none disabled:opacity-50",
              checked ? "bg-surface-2 font-medium text-foreground" : "text-muted hover:text-foreground",
            )}
          >
            {tf}
          </button>
        );
      })}
    </div>
  );
}
