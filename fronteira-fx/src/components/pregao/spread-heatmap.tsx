"use client";
import type { ReactElement } from "react";
import { Skeleton } from "@/components/ui/skeleton";
import { formatPercent } from "@/lib/format";
import { PAIR_LABEL, PAIRS, type HeatCell, type PairKey } from "@/lib/pregao/types";
import { cn } from "@/lib/utils";

export type HeatStep = 0 | 1 | 2 | 3 | 4 | 5;

export const HEAT_LEGEND: readonly { step: 1 | 2 | 3 | 4 | 5; label: string }[] = [
  { step: 1, label: "< 0,5 %" },
  { step: 2, label: "0,5–1 %" },
  { step: 3, label: "1–2 %" },
  { step: 4, label: "2–4 %" },
  { step: 5, label: "≥ 4 %" },
];

/** Classes escritas por inteiro: o Tailwind só gera o que aparece completo no código-fonte. */
const HEAT_BG: Record<HeatStep, string | undefined> = {
  0: undefined,
  1: "bg-[var(--heat-1)]",
  2: "bg-[var(--heat-2)]",
  3: "bg-[var(--heat-3)]",
  4: "bg-[var(--heat-4)]",
  5: "bg-[var(--heat-5)]",
};

function hasSpread(v: number | null): v is number {
  return v !== null && !Number.isNaN(v);
}

/** Degrau da escala sequencial a partir do spread já ×100 (`1.1784` = 1,18 %). */
export function heatStep(spreadPct: number | null): HeatStep {
  if (!hasSpread(spreadPct)) return 0;
  if (spreadPct < 0.5) return 1;
  if (spreadPct < 1) return 2;
  if (spreadPct < 2) return 3;
  if (spreadPct < 4) return 4;
  return 5;
}

export function heatCellLabel(cell: HeatCell): string {
  if (!hasSpread(cell.spread_pct)) return "sem spread";
  const closed = cell.status === "closed" ? ", fechada" : "";
  return `${cell.house}, ${PAIR_LABEL[cell.pair]}: spread ${formatPercent(cell.spread_pct / 100)}${closed}`;
}

export interface SpreadHeatmapProps {
  cells: HeatCell[];
  houses: readonly { source_id: string; house: string }[];
  pairs?: readonly PairKey[];
  selectedKey: string | null;
  onSelect: (key: string) => void;
  loading?: boolean;
  className?: string;
}

/** Uma célula por (casa, par); se houver várias, vale a de `captured_at` mais recente. */
function latestCells(cells: HeatCell[], houseIds: ReadonlySet<string>): Map<string, Map<PairKey, HeatCell>> {
  const index = new Map<string, Map<PairKey, HeatCell>>();
  for (const cell of cells) {
    if (!houseIds.has(cell.source_id)) continue;
    let row = index.get(cell.source_id);
    if (!row) {
      row = new Map();
      index.set(cell.source_id, row);
    }
    const prev = row.get(cell.pair);
    if (!prev || Date.parse(cell.captured_at) > Date.parse(prev.captured_at)) row.set(cell.pair, cell);
  }
  return index;
}

function heatTd(cell: HeatCell | null, pair: PairKey, selectedKey: string | null, onSelect: (key: string) => void): ReactElement {
  if (cell === null) {
    return (
      <td key={pair} data-step={0}>
        <button
          type="button"
          data-testid="pregao-heat-cell"
          aria-label="sem spread"
          aria-pressed={false}
          disabled
          className="tnum h-8 w-full text-foreground max-md:h-10"
        >
          —
        </button>
      </td>
    );
  }
  const step = heatStep(cell.spread_pct);
  const shown = hasSpread(cell.spread_pct) ? formatPercent(cell.spread_pct / 100) : "—";
  return (
    <td key={pair} data-step={step} className={HEAT_BG[step]}>
      <button
        type="button"
        data-testid="pregao-heat-cell"
        data-key={cell.key}
        aria-label={heatCellLabel(cell)}
        aria-pressed={cell.key === selectedKey}
        disabled={step === 0}
        className={cn("tnum h-8 w-full text-foreground max-md:h-10", cell.status === "closed" && "border border-dashed border-border-strong")}
        onClick={() => onSelect(cell.key)}
      >
        {shown}
      </button>
    </td>
  );
}

/** Matriz casa × par com o spread %; cada célula é um botão que devolve a chave da série. */
export function SpreadHeatmap({
  cells,
  houses,
  pairs = PAIRS,
  selectedKey,
  onSelect,
  loading = false,
  className,
}: SpreadHeatmapProps): ReactElement {
  if (loading) {
    return (
      <div data-testid="pregao-heatmap" data-state="loading" aria-busy="true" className={cn("grid gap-2", className)}>
        <Skeleton className="h-40 w-full" />
        <span className="sr-only">Carregando…</span>
      </div>
    );
  }

  const hasContent = houses.length > 0 && cells.some((c) => hasSpread(c.spread_pct));
  if (!hasContent) {
    return (
      <div data-testid="pregao-heatmap" data-state="empty" className={cn("grid gap-2", className)}>
        <p className="text-sm text-muted">Sem spreads para montar o mapa.</p>
      </div>
    );
  }

  const index = latestCells(cells, new Set(houses.map((h) => h.source_id)));

  return (
    <div data-testid="pregao-heatmap" data-state="ready" className={cn("grid gap-2", className)}>
      <div className="relative overflow-x-auto">
        <table className="text-[13px]">
          <caption className="sr-only">Spread por casa e par</caption>
          <thead>
            <tr>
              <th scope="col">
                <span className="sr-only">Casa</span>
              </th>
              {pairs.map((p) => (
                <th key={p} scope="col" className="px-2 text-right font-medium">
                  {PAIR_LABEL[p]}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {houses.map((h) => (
              <tr key={h.source_id}>
                <th scope="row" className="whitespace-nowrap pr-3 text-left font-medium">
                  {h.house}
                </th>
                {pairs.map((p) => heatTd(index.get(h.source_id)?.get(p) ?? null, p, selectedKey, onSelect))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ol aria-label="Legenda do spread" className="flex flex-wrap gap-2 text-[11px] text-muted">
        {HEAT_LEGEND.map(({ step, label }) => (
          <li key={step} className="flex items-center gap-1">
            <span aria-hidden className={cn("inline-block h-3 w-3 border border-border", HEAT_BG[step])} />
            {label}
          </li>
        ))}
      </ol>
    </div>
  );
}
