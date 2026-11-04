"use client";
import { useState, type KeyboardEvent as ReactKeyboardEvent, type ReactElement } from "react";
import { createColumnHelper, flexRender, getCoreRowModel, getSortedRowModel, useReactTable, type SortingState } from "@tanstack/react-table";
import { ArrowDown, ArrowUp } from "lucide-react";
import { CITY_LABEL } from "@/lib/api/types";
import { formatPercent, formatRate, toNumber } from "@/lib/format";
import { quoteOfPair } from "@/lib/pregao/candles";
import { PAIR_LABEL, STATUS_BADGE, STATUS_LABEL, type WatchlistRow } from "@/lib/pregao/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { cn } from "@/lib/utils";
import { Delta } from "@/components/pregao/delta";
import { HouseCity } from "@/components/pregao/house-city";
import { ReferenceBadge } from "@/components/pregao/reference-badge";
import { Sparkline } from "@/components/pregao/sparkline";

export interface WatchlistProps {
  rows: WatchlistRow[];
  selectedKey: string | null;
  onSelect: (key: string) => void;
  loading?: boolean;
  error?: Error | null;
  onRetry?: () => void;
  className?: string;
}

export const WATCHLIST_COLUMNS: readonly string[] = ["pair", "house", "city", "buy", "sell", "spread", "delta", "trend", "status"];

const NUMERIC = new Set(["buy", "sell", "spread", "delta"]);
/**
 * Abaixo de sm (celular) ficam casa, compra, venda e variação. O par já está escolhido no seletor acima; cidade e
 * estado descem para a célula da casa (sigla e selo), como no livro.
 */
const HIDDEN_BELOW_SM = new Set(["pair", "city", "spread", "trend", "status"]);
/**
 * Tendência (sparkline, 88 px) sai abaixo de xl: no tablet (1024 px) a tabela inteira passava da borda do painel
 * (19 a 26 px). Sem ela, casa, cidade, preços e estado cabem no painel.
 */
const HIDDEN_BELOW_XL = new Set(["trend"]);
/** Nenhuma célula quebra linha: números não se partem ("≈" de um lado, número do outro) e casa/cidade truncam com title. */
const NOWRAP = new Set(["pair", "house", "city", "buy", "sell", "spread", "delta"]);

const col = createColumnHelper<WatchlistRow>();

/**
 * Casa com selo de referência e aviso de incompleta, numa linha só (nome truncado, inteiro no title); a referência
 * nunca é clicável. Abaixo de sm, sem as colunas Cidade e Estado, a sigla da cidade e o estado vêm logo abaixo do
 * nome: a mesma casa aparece uma vez por filial e precisa ser distinguível.
 */
function HouseCell({ row }: { row: WatchlistRow }): ReactElement {
  const title = row.city ? `${row.house} · ${CITY_LABEL[row.city]}` : row.house;
  const ref = row.kind === "market_reference";
  return (
    <span className="flex min-w-0 flex-col gap-0.5">
      <span className="inline-flex flex-nowrap items-center gap-1.5">
        <span className="max-w-[10rem] truncate" title={title}>
          {row.house}
        </span>
        {/* No celular o selo de referência desce para a linha de baixo: a coluna Casa não alarga por causa dele. */}
        {ref ? <ReferenceBadge compact className="shrink-0 max-sm:hidden" /> : null}
        {row.incomplete ? <Badge variant="warn">incompleta</Badge> : null}
      </span>
      <span data-testid="pregao-watchlist-house-sub" className="flex flex-nowrap items-center gap-1.5 sm:hidden">
        <HouseCity city={row.city} testId="pregao-watchlist-city" />
        {ref ? <ReferenceBadge compact className="shrink-0" /> : null}
        <StatusBadge status={row.status} />
      </span>
    </span>
  );
}

function StatusBadge({ status }: { status: WatchlistRow["status"] }): ReactElement {
  return (
    <Badge variant={STATUS_BADGE[status]} data-testid="pregao-watchlist-status">
      {STATUS_LABEL[status]}
    </Badge>
  );
}

/** Cidade: nome inteiro em xl; abaixo, a sigla (CDE/ASU/PJC) com o nome no title, como no livro. Digital: "Digital". */
function CityCell({ row }: { row: WatchlistRow }): ReactElement {
  if (row.city === null) return <span>{CITY_LABEL.digital}</span>;
  return (
    <>
      <span className="block max-w-[10rem] truncate max-xl:hidden" title={CITY_LABEL[row.city]}>
        {CITY_LABEL[row.city]}
      </span>
      <HouseCity city={row.city} testId="pregao-watchlist-city" className="text-[13px] text-foreground xl:hidden" />
    </>
  );
}

/** Compra/Venda na moeda de cotação do par; referências ganham prefixo "≈ ". */
function rateText(row: WatchlistRow, side: "buy" | "sell"): string {
  const text = formatRate(row[side], quoteOfPair(row.pair));
  return row.kind === "market_reference" ? `≈ ${text}` : text;
}

function spreadText(spread: number | null): string {
  return formatPercent(spread === null ? null : spread / 100);
}

function ariaSort(sorted: false | "asc" | "desc"): "ascending" | "descending" | "none" {
  if (sorted === "asc") return "ascending";
  if (sorted === "desc") return "descending";
  return "none";
}

// Colunas na ordem de WATCHLIST_COLUMNS. Definidas fora do componente: estáveis entre renderizações.
const columns = [
  col.accessor("pair", { id: "pair", header: "Par", cell: (c) => PAIR_LABEL[c.getValue()] }),
  col.accessor("house", { id: "house", header: "Casa", cell: (c) => <HouseCell row={c.row.original} /> }),
  col.accessor((r) => (r.city ? CITY_LABEL[r.city] : CITY_LABEL.digital), { id: "city", header: "Cidade", cell: (c) => <CityCell row={c.row.original} /> }),
  col.accessor((r) => toNumber(r.buy) ?? undefined, { id: "buy", header: "Compra", sortUndefined: "last", cell: (c) => rateText(c.row.original, "buy") }),
  col.accessor((r) => toNumber(r.sell) ?? undefined, { id: "sell", header: "Venda", sortUndefined: "last", cell: (c) => rateText(c.row.original, "sell") }),
  col.accessor((r) => r.spread_pct ?? undefined, { id: "spread", header: "Spread", sortUndefined: "last", cell: (c) => spreadText(c.row.original.spread_pct) }),
  col.accessor((r) => r.change_pct ?? undefined, { id: "delta", header: "Δ dia", sortUndefined: "last", cell: (c) => <Delta value={c.row.original.change_pct} /> }),
  col.display({ id: "trend", header: "Tendência", enableSorting: false, cell: (c) => <Sparkline values={c.row.original.spark} /> }),
  col.accessor("status", { id: "status", header: "Estado", cell: (c) => <StatusBadge status={c.getValue()} /> }),
];

/** Move o foco para a linha focável vizinha dentro da mesma tabela (↑/↓). */
function focusSibling(current: HTMLElement, step: 1 | -1): void {
  const body = current.closest("tbody");
  if (!body) return;
  const focusable = Array.from(body.querySelectorAll<HTMLElement>('tr[tabindex="0"]'));
  focusable[focusable.indexOf(current) + step]?.focus();
}

/** Lista de séries acompanhadas: ordenável, navegável por teclado, números tabulares. */
export function Watchlist({ rows, selectedKey, onSelect, loading = false, error = null, onRetry, className }: WatchlistProps): ReactElement {
  const [sorting, setSorting] = useState<SortingState>([{ id: "spread", desc: false }]);
  const table = useReactTable({
    data: rows,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  const demo = rows.some((r) => r.data_mode === "demo");
  const mode = demo ? "demo" : undefined;

  if (loading) {
    return (
      <div data-testid="pregao-watchlist" data-state="loading" aria-busy="true" data-mode={mode} className={className}>
        <Skeleton className="h-40 w-full" />
        <span className="sr-only">Carregando…</span>
      </div>
    );
  }

  if (error) {
    return (
      <div data-testid="pregao-watchlist" data-state="error" data-mode={mode} className={className}>
        <div role="alert" className="flex flex-wrap items-center gap-2 text-sm">
          <span>Não foi possível carregar a lista.</span>
          <span className="text-muted">{error.message}</span>
          {onRetry ? (
            <Button variant="outline" size="sm" onClick={onRetry}>
              Tentar de novo
            </Button>
          ) : null}
        </div>
      </div>
    );
  }

  if (rows.length === 0) {
    return (
      <div data-testid="pregao-watchlist" data-state="empty" data-mode={mode} className={className}>
        <p className="text-sm text-muted">Nenhuma série na lista.</p>
      </div>
    );
  }

  const handleRowKey = (e: ReactKeyboardEvent<HTMLTableRowElement>, key: string) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      onSelect(key);
    } else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      focusSibling(e.currentTarget, e.key === "ArrowDown" ? 1 : -1);
    }
  };

  return (
    <div data-testid="pregao-watchlist" data-state="ready" data-mode={mode} className={className}>
      {/* No celular as células perdem 2 px de cada lado: casa, compra, venda e variação cabem em 358 px. */}
      <Table className="text-[13px] max-sm:[&_td]:px-1.5 max-sm:[&_th]:px-1.5">
        <caption className="sr-only">Lista de séries acompanhadas</caption>
        <TableHeader>
          {table.getHeaderGroups().map((group) => (
            <TableRow key={group.id} className="hover:bg-transparent">
              {group.headers.map((header) => {
                const id = header.column.id;
                const sorted = header.column.getIsSorted();
                const label = flexRender(header.column.columnDef.header, header.getContext());
                return (
                  <TableHead
                    key={header.id}
                    scope="col"
                    aria-sort={header.column.getCanSort() ? ariaSort(sorted) : undefined}
                    className={cn(
                      NUMERIC.has(id) && "text-right",
                      HIDDEN_BELOW_SM.has(id) && "max-sm:hidden",
                      HIDDEN_BELOW_XL.has(id) && "max-xl:hidden",
                    )}
                  >
                    {header.column.getCanSort() ? (
                      <button
                        type="button"
                        className="inline-flex items-center gap-1 hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring"
                        onClick={header.column.getToggleSortingHandler()}
                      >
                        {label}
                        {sorted === "asc" ? <ArrowUp className="size-3" aria-hidden /> : null}
                        {sorted === "desc" ? <ArrowDown className="size-3" aria-hidden /> : null}
                      </button>
                    ) : (
                      label
                    )}
                  </TableHead>
                );
              })}
            </TableRow>
          ))}
        </TableHeader>
        <TableBody>
          {table.getRowModel().rows.map((row) => {
            const r = row.original;
            const isRef = r.kind === "market_reference";
            const selected = !isRef && r.key === selectedKey;
            return (
              <TableRow
                key={row.id}
                data-testid="pregao-watchlist-row"
                data-key={r.key}
                data-kind={r.kind}
                data-status={r.status}
                data-state={selected ? "selected" : undefined}
                aria-selected={selected}
                tabIndex={isRef ? -1 : 0}
                aria-disabled={isRef ? "true" : undefined}
                className={cn(
                  "h-8 max-md:h-10",
                  isRef ? "border-l-2 border-dashed border-border" : "cursor-pointer focus-visible:outline-2 focus-visible:outline-ring focus-visible:-outline-offset-2",
                )}
                onClick={isRef ? undefined : () => onSelect(r.key)}
                onKeyDown={isRef ? undefined : (e) => handleRowKey(e, r.key)}
              >
                {row.getVisibleCells().map((cell) => {
                  const id = cell.column.id;
                  return (
                    <TableCell
                      key={cell.id}
                      data-col={id}
                      className={cn(
                        NUMERIC.has(id) && "text-right tnum",
                        NOWRAP.has(id) && "whitespace-nowrap",
                        HIDDEN_BELOW_SM.has(id) && "max-sm:hidden",
                        HIDDEN_BELOW_XL.has(id) && "max-xl:hidden",
                      )}
                    >
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </TableCell>
                  );
                })}
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
