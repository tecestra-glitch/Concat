"use client";
/**
 * Crédito Uiverse.io: slug `abas-segmentadas`; elemento zanina-yassine_curly-shrimp-52; autor zanina-yassine; licença MIT; link https://uiverse.io/zanina-yassine/curly-shrimp-52
 * Texto completo da licença: docs/creditos-uiverse.md.
 */
/**
 * Abas segmentadas. Elemento Uiverse «abas-segmentadas» (zanina-yassine), MIT, Uiverse.io. O indicador desliza por
 * transform (nunca por left), em --motion-base. Semântica de `role="tablist"` com setas, Home e End.
 */
import * as React from "react";
import { cn } from "@/lib/utils";

export interface FxSegmentedItem<T extends string> {
  id: T;
  label: string;
}

export interface FxSegmentedProps<T extends string> {
  items: readonly FxSegmentedItem<T>[];
  value: T;
  onValueChange: (id: T) => void;
  /** Prefixo dos ids das abas (`${idPrefix}-${id}`), para `aria-controls` nos painéis. */
  idPrefix: string;
  "aria-label": string;
  testId?: string;
  className?: string;
}

/** Próxima aba para uma tecla: setas cíclicas, Home e End. Outras teclas → `null`. */
export function segmentedNext<T extends string>(items: readonly FxSegmentedItem<T>[], current: T, key: string): T | null {
  const i = items.findIndex((t) => t.id === current);
  switch (key) {
    case "ArrowRight":
      return items[(i + 1) % items.length].id;
    case "ArrowLeft":
      return items[(i - 1 + items.length) % items.length].id;
    case "Home":
      return items[0].id;
    case "End":
      return items[items.length - 1].id;
    default:
      return null;
  }
}

export function FxSegmented<T extends string>({ items, value, onValueChange, idPrefix, testId, className, ...aria }: FxSegmentedProps<T>) {
  const index = Math.max(0, items.findIndex((t) => t.id === value));
  const n = items.length;

  function onKeyDown(e: React.KeyboardEvent<HTMLDivElement>) {
    const next = segmentedNext(items, value, e.key);
    if (next === null) return;
    e.preventDefault();
    onValueChange(next);
    e.currentTarget.querySelector<HTMLButtonElement>(`#${idPrefix}-${next}`)?.focus();
  }

  return (
    <div
      role="tablist"
      aria-label={aria["aria-label"]}
      data-testid={testId}
      onKeyDown={onKeyDown}
      className={cn("relative grid rounded-control border border-border bg-surface-2 p-1", className)}
      style={{ gridTemplateColumns: `repeat(${n}, minmax(0, 1fr))` }}
    >
      <span
        aria-hidden
        className="fx-segmented-indicator pointer-events-none absolute inset-y-1 left-1 rounded-chip border border-border bg-surface-3"
        style={{ width: `calc((100% - 0.5rem) / ${n})`, "--i": index } as React.CSSProperties}
      />
      {items.map((item) => {
        const active = item.id === value;
        return (
          <button
            key={item.id}
            type="button"
            role="tab"
            id={`${idPrefix}-${item.id}`}
            aria-selected={active}
            tabIndex={active ? 0 : -1}
            onClick={() => onValueChange(item.id)}
            className={cn(
              "relative z-10 min-h-11 rounded-chip px-2 text-body font-medium transition-colors duration-(--motion-fast) sm:min-h-8",
              "focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2",
              active ? "text-foreground" : "text-muted hover:text-foreground",
            )}
          >
            {item.label}
          </button>
        );
      })}
    </div>
  );
}
