"use client";
import type { KeyboardEvent, ReactElement } from "react";
import { rovingIndex } from "@/components/pregao/timeframe-bar";
import { FxChoice } from "@/components/ui/fx/fx-choice";
import { PairFlags, type FlagCode } from "@/components/ui/currency-flag";
import { PAIRS, type PairKey } from "@/lib/pregao/types";
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
      className={cn("inline-flex max-w-full flex-wrap rounded-control border border-border bg-surface p-0.5", className)}
    >
      {pairs.map((pair) => {
        const checked = pair === value;
        return (
          <FxChoice
            key={pair}
            checked={checked}
            data-pair={pair}
            tabIndex={pair === tabStop ? 0 : -1}
            disabled={disabled}
            onClick={() => onChange(pair)}
          >
            <PairFlags base={pair.split("/")[0] as FlagCode} quote={pair.split("/")[1] as FlagCode} />
          </FxChoice>
        );
      })}
    </div>
  );
}
