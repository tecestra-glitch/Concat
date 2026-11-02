"use client";
import type { KeyboardEvent, ReactElement } from "react";
import { rovingIndex } from "@/components/pregao/timeframe-bar";
import { PAIRS, PAIR_LABEL, type PairKey } from "@/lib/pregao/types";
import { cn } from "@/lib/utils";

export interface PairSelectorProps {
  value: PairKey;
  pairs?: readonly PairKey[];
  onChange: (pair: PairKey) => void;
  disabled?: boolean;
  className?: string;
}

/** Seletor de par de moedas. `[` e `]` trocam o par na página (F17). */
export function PairSelector({ value, pairs = PAIRS, onChange, disabled = false, className }: PairSelectorProps): ReactElement {
  const current = Math.max(0, pairs.indexOf(value));
  // Se o valor não estiver na lista, o primeiro par continua acessível pela tabulação.
  const tabStop = pairs.includes(value) ? value : pairs[0];

  function onKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    if (disabled) return;
    const idx = rovingIndex(current, e.key, pairs.length);
    if (idx === null) return;
    e.preventDefault();
    onChange(pairs[idx]);
    e.currentTarget.querySelectorAll<HTMLElement>('[role="radio"]')[idx].focus();
  }

  return (
    <div
      role="radiogroup"
      aria-label="Par de moedas ([ e ] trocam o par)"
      data-testid="pregao-pair"
      onKeyDown={onKeyDown}
      className={cn("inline-flex rounded-md border border-border bg-surface p-0.5", className)}
    >
      {pairs.map((pair) => {
        const checked = pair === value;
        return (
          <button
            key={pair}
            type="button"
            role="radio"
            aria-checked={checked}
            data-pair={pair}
            tabIndex={pair === tabStop ? 0 : -1}
            disabled={disabled}
            onClick={() => onChange(pair)}
            className={cn(
              "tnum h-8 max-sm:h-10 min-w-10 rounded-sm px-2.5 text-[13px] transition-colors",
              "focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2",
              "disabled:pointer-events-none disabled:opacity-50",
              checked ? "bg-surface-2 font-medium text-foreground" : "text-muted hover:text-foreground",
            )}
          >
            {PAIR_LABEL[pair]}
          </button>
        );
      })}
    </div>
  );
}
