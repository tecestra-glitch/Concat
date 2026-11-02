"use client";
import type { KeyboardEvent, ReactElement } from "react";
import { Landmark, Store } from "lucide-react";
import { AgioBadge } from "@/components/pregao/agio-badge";
import { ReferenceBadge } from "@/components/pregao/reference-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import type { Currency } from "@/lib/api/types";
import { formatAge, formatRate, toNumber } from "@/lib/format";
import type { BookLevel, PairKey } from "@/lib/pregao/types";
import { cn } from "@/lib/utils";

export interface BookSides {
  bids: BookLevel[];
  asks: BookLevel[];
  refs: BookLevel[];
}

export interface BookLadderProps {
  levels: BookLevel[]; // casas e referências misturadas; o componente separa
  pair: PairKey;
  quote: Currency;
  selectedKey: string | null;
  onSelect: (key: string) => void;
  now: number; // ms epoch; 0 = omitir idades
  loading?: boolean;
  error?: Error | null;
  onRetry?: () => void;
  className?: string;
}

function byHouse(a: BookLevel, b: BookLevel): number {
  return a.house.localeCompare(b.house, "pt-BR");
}

/**
 * Separa o livro em lados e referências (§15.2). Compra: melhor compra (maior) primeiro; venda: melhor
 * venda (menor) primeiro; empate por nome da casa. Referência (`market_reference`) nunca entra nos lados.
 */
export function splitBook(levels: BookLevel[]): BookSides {
  const houses = levels.filter((l) => l.kind !== "market_reference");
  const bids = houses.filter((l) => l.buy !== null).sort((a, b) => Number(b.buy) - Number(a.buy) || byHouse(a, b));
  const asks = houses.filter((l) => l.sell !== null).sort((a, b) => Number(a.sell) - Number(b.sell) || byHouse(a, b));
  const refs = levels.filter((l) => l.kind === "market_reference");
  return { bids, asks, refs };
}

function refValue(level: BookLevel, quote: Currency): string {
  const { buy, sell } = level;
  if (buy !== null && sell !== null && toNumber(buy) !== toNumber(sell)) {
    return `${formatRate(buy, quote)} / ${formatRate(sell, quote)}`;
  }
  return formatRate(buy ?? sell, quote);
}

interface BookRowProps {
  level: BookLevel;
  side: "buy" | "sell";
  best: boolean;
  quote: Currency;
  selected: boolean;
  now: number;
  onSelect: (key: string) => void;
}

function BookRow({ level, side, best, quote, selected, now, onSelect }: BookRowProps): ReactElement {
  const price = side === "buy" ? level.buy : level.sell;
  const agio = side === "buy" ? level.agio_buy_pct : level.agio_sell_pct;
  const closed = level.status === "closed";

  function onKeyDown(ev: KeyboardEvent<HTMLTableRowElement>) {
    if (ev.key === "Enter" || ev.key === " ") {
      ev.preventDefault();
      onSelect(level.key);
    }
  }

  return (
    <tr
      data-testid="pregao-book-row"
      data-key={level.key}
      data-side={side}
      data-best={best ? "true" : "false"}
      data-status={level.status}
      tabIndex={0}
      aria-selected={selected}
      className={cn(
        "h-8 max-md:h-10 cursor-pointer hover:bg-surface-2 focus-visible:outline-2 focus-visible:outline-ring aria-selected:ring-1 aria-selected:ring-inset aria-selected:ring-accent",
        best && "bg-surface-2 font-semibold",
      )}
      onClick={() => onSelect(level.key)}
      onKeyDown={onKeyDown}
    >
      <td className="pr-2">
        <span className="inline-flex flex-wrap items-center gap-1">
          <Store size={12} aria-hidden />
          {level.house}
          {best && <Badge variant="accent">melhor</Badge>}
          {closed && <Badge variant="outline">fechada</Badge>}
          {level.incomplete && <Badge variant="warn">incompleta</Badge>}
        </span>
      </td>
      <td className="tnum text-right text-foreground">{formatRate(price, quote)}</td>
      <td className="text-right">
        <AgioBadge value={agio} />
      </td>
      <td className="tnum text-right text-muted max-sm:hidden">{now > 0 ? formatAge(level.captured_at, now) : "—"}</td>
    </tr>
  );
}

interface SideTableProps {
  side: "buy" | "sell";
  rows: BookLevel[];
  quote: Currency;
  selectedKey: string | null;
  onSelect: (key: string) => void;
  now: number;
}

function SideTable({ side, rows, quote, selectedKey, onSelect, now }: SideTableProps): ReactElement {
  return (
    <table className="w-full text-[13px]">
      <caption className="sr-only">{side === "buy" ? "Lado da compra" : "Lado da venda"}</caption>
      <thead>
        <tr className="text-left text-muted">
          <th scope="col" className="font-medium">Casa</th>
          <th scope="col" className="text-right font-medium">Preço</th>
          <th scope="col" className="text-right font-medium">Ágio vs BCP</th>
          <th scope="col" className="text-right font-medium max-sm:hidden">Idade</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((level, i) => (
          <BookRow
            key={level.key}
            level={level}
            side={side}
            best={i === 0}
            quote={quote}
            selected={selectedKey === level.key}
            now={now}
            onSelect={onSelect}
          />
        ))}
      </tbody>
    </table>
  );
}

function RefTable({ rows, quote, now }: { rows: BookLevel[]; quote: Currency; now: number }): ReactElement {
  return (
    <table className="w-full text-[13px]">
      <caption className="sr-only">Preços de referência do par</caption>
      <thead>
        <tr className="text-left text-muted">
          <th scope="col" className="font-medium">Casa</th>
          <th scope="col" className="text-right font-medium">Valor</th>
          <th scope="col" className="text-right font-medium max-sm:hidden">Idade</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((level) => (
          <tr key={level.key} data-testid="pregao-book-ref-row" data-kind="market_reference" data-key={level.key} className="h-8 max-md:h-10">
            <td className="pr-2">
              <span className="inline-flex flex-wrap items-center gap-1">
                <Landmark size={12} aria-hidden />
                {level.house}
                <ReferenceBadge compact source={level.source_id} />
              </span>
            </td>
            <td className="tnum text-right text-muted">{`≈ ${refValue(level, quote)}`}</td>
            <td className="tnum text-right text-muted max-sm:hidden">{now > 0 ? formatAge(level.captured_at, now) : "—"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** Livro de casas para um par: formadores de mercado por lado, referência em bloco separado (F7). */
export function BookLadder({
  levels,
  pair,
  quote,
  selectedKey,
  onSelect,
  now,
  loading = false,
  error = null,
  onRetry,
  className,
}: BookLadderProps): ReactElement {
  const { bids, asks, refs } = splitBook(levels);
  const demo = levels.some((l) => l.data_mode === "demo");
  const shared = { "data-testid": "pregao-book", "data-pair": pair, "data-mode": demo ? "demo" : undefined } as const;

  if (loading) {
    return (
      <div {...shared} data-state="loading" aria-busy="true" className={cn("grid gap-3", className)}>
        <Skeleton className="h-48" />
        <span className="sr-only">Carregando…</span>
      </div>
    );
  }

  if (error) {
    return (
      <div {...shared} data-state="error" className={cn("grid gap-3", className)}>
        <div role="alert" className="text-sm">
          Não foi possível carregar o livro. <span className="text-muted">{error.message}</span>
          {onRetry && (
            <Button variant="outline" size="sm" className="ml-2" onClick={onRetry}>
              Tentar de novo
            </Button>
          )}
        </div>
      </div>
    );
  }

  if (bids.length === 0 && asks.length === 0) {
    return (
      <div {...shared} data-state="empty" className={cn("grid gap-3", className)}>
        <p className="text-sm text-muted">Nenhuma casa publicou cotação para este par.</p>
      </div>
    );
  }

  return (
    <div {...shared} data-state="ready" className={cn("@container grid gap-3", className)}>
      {/* Lado a lado só quando o próprio bloco tem ≥ 28rem: em lg+ o livro mora numa coluna de 20rem. */}
      <div className="grid gap-3 @md:grid-cols-2">
        <section aria-labelledby="pregao-book-buy-h" data-testid="pregao-book-side-buy" className="min-w-0">
          <h4 id="pregao-book-buy-h" className="text-sm font-medium">Compra</h4>
          <p className="text-xs text-muted">quanto a casa paga</p>
          <SideTable side="buy" rows={bids} quote={quote} selectedKey={selectedKey} onSelect={onSelect} now={now} />
        </section>
        <section aria-labelledby="pregao-book-sell-h" data-testid="pregao-book-side-sell" className="min-w-0">
          <h4 id="pregao-book-sell-h" className="text-sm font-medium">Venda</h4>
          <p className="text-xs text-muted">quanto a casa cobra</p>
          <SideTable side="sell" rows={asks} quote={quote} selectedKey={selectedKey} onSelect={onSelect} now={now} />
        </section>
      </div>
      <section
        aria-labelledby="pregao-book-ref-h"
        data-testid="pregao-book-reference"
        className="rounded-md border border-dashed border-border p-2"
      >
        <h4 id="pregao-book-ref-h" className="text-sm font-medium">Referências</h4>
        <p className="text-xs text-muted">Preço de referência, não executável. Não é uma casa.</p>
        {refs.length === 0 ? (
          <p className="mt-2 text-sm text-muted">Sem referência para este par.</p>
        ) : (
          <RefTable rows={refs} quote={quote} now={now} />
        )}
      </section>
    </div>
  );
}
