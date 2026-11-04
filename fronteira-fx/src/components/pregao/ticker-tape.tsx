"use client";
import type { ReactElement } from "react";
import { Delta } from "@/components/pregao/delta";
import { ReferenceBadge } from "@/components/pregao/reference-badge";
import { CurrencyFlag, type FlagCode } from "@/components/ui/currency-flag";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { TriangleAlert } from "lucide-react";
import { formatRate } from "@/lib/format";
import { quoteOfPair } from "@/lib/pregao/candles";
import { PAIR_LABEL, type TickerItem } from "@/lib/pregao/types";
import { cn } from "@/lib/utils";

export interface TickerTapeProps {
  items: TickerItem[];
  selectedKey?: string | null;
  onSelect?: (key: string) => void;
  loading?: boolean;
  className?: string;
}

/** Rótulo acessível de um item: "USD/PYG Cambios Chaco 7.335" (mid nulo → "—"). */
export function tickerLabel(item: TickerItem): string {
  return `${PAIR_LABEL[item.pair]} ${item.house} ${formatRate(item.mid, quoteOfPair(item.pair))}`;
}

function TickerTapeItem({ item, selected, onSelect }: { item: TickerItem; selected: boolean; onSelect?: (key: string) => void }): ReactElement {
  const isReference = item.kind === "market_reference";
  const [base, quote] = item.pair.split("/") as [FlagCode, FlagCode];
  const value = (
    <>
      <span className={cn("inline-flex items-center gap-1.5 font-medium", selected && "text-accent")}>
        <CurrencyFlag code={base} />
        <span aria-hidden="true" className="text-muted">/</span>
        <CurrencyFlag code={quote} />
      </span>
      <span className="text-muted">{item.house}</span>
      <span className="fx-num">
        {isReference ? "≈ " : null}
        {formatRate(item.mid, quoteOfPair(item.pair))}
        {isReference ? <ReferenceBadge compact source={item.source_id} className="ml-1" /> : null}
      </span>
    </>
  );

  return (
    <li data-testid="pregao-ticker-item" data-key={item.key} data-kind={item.kind} className="flex items-center gap-2 whitespace-nowrap">
      {isReference || !onSelect ? (
        <span className="inline-flex items-center gap-2">{value}</span>
      ) : (
        <button
          type="button"
          aria-label={tickerLabel(item)}
          aria-current={selected ? "true" : undefined}
          onClick={() => onSelect(item.key)}
          className="inline-flex min-h-11 items-center gap-2 rounded-chip px-1 md:min-h-8 focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2"
        >
          {value}
        </button>
      )}
      <Delta value={item.change_pct} />
      {item.incomplete ? (
        <Badge variant="warn">
          <TriangleAlert size={12} aria-hidden />
          <span className="sr-only">cotação incompleta</span>
        </Badge>
      ) : null}
    </li>
  );
}

/**
 * Fita de cotações estática (dev/ui/spec-reforma-ui.md, PR1): sem laço, sem animação e sem botão de pausa. As cotações
 * ficam em linha e a rolagem é horizontal e manual (`overflow-x-auto`), então nada se move sozinho sobre um número.
 */
export function TickerTape({ items, selectedKey = null, onSelect, loading = false, className }: TickerTapeProps): ReactElement {
  const state = loading ? "loading" : items.length === 0 ? "empty" : "ready";
  const demo = items.some((i) => i.data_mode === "demo");

  return (
    <div
      role="region"
      aria-label="Fita de cotações"
      data-testid="pregao-ticker"
      data-state={state}
      data-mode={demo ? "demo" : undefined}
      aria-busy={loading ? "true" : undefined}
      className={cn("flex min-w-0 items-stretch overflow-hidden border-y border-border bg-surface", className)}
    >
      {state === "loading" ? (
        <>
          <Skeleton className="h-8 w-full" />
          <span className="sr-only">Carregando…</span>
        </>
      ) : state === "empty" ? (
        <p className="p-2 text-body text-muted">Sem cotações na fita.</p>
      ) : (
        // `contain: paint` (classe abaixo) impede que a lista larga (w-max) entre na largura da página.
        <div role="group" data-testid="pregao-ticker-scroll" tabIndex={0} aria-label="Cotações, role para o lado" className="min-w-0 flex-1 overflow-x-auto [contain:paint] focus-visible:outline-2 focus-visible:outline-ring">
          <ul className="flex w-max gap-6 px-3 py-1.5 text-body">
            {items.map((item) => (
              <TickerTapeItem key={item.key} item={item} selected={item.key === selectedKey} onSelect={onSelect} />
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
