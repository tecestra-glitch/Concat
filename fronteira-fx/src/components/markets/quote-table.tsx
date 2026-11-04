"use client";
import * as React from "react";
import { createColumnHelper, flexRender, getCoreRowModel, getSortedRowModel, useReactTable, type SortingState, type VisibilityState } from "@tanstack/react-table";
import { ArrowUpDown, Landmark } from "lucide-react";
import type { Quote, Source } from "@/lib/api/types";
import { CITY_LABEL, MODALITY_LABEL } from "@/lib/api/types";
import { formatAge, formatPercent, ageSeconds } from "@/lib/format";
import { formatRateFixed } from "@/components/ui/rate";
import { Table, TableBody, TableCaption, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { FlagIcon } from "@/components/ui/currency-flag";
import { EmptyState } from "@/components/ui/empty-state";
import { sourceCountry } from "@/lib/api/source-country";
import { cn } from "@/lib/utils";
import { useNow } from "@/lib/use-now";

const col = createColumnHelper<Quote>();
const RIGHT = new Set(["buy", "sell", "spread", "age"]);
const COMPACT_HIDDEN: VisibilityState = { spread: false, modality: false, kind: false };
const ALL_VISIBLE: VisibilityState = {};

/** Spread relativo à média de compra e venda, como razão (0.0118 = 1,18 %). */
export function spreadRatio(q: Quote): number | null {
  if (q.buy === null || q.sell === null) return null;
  const b = Number(q.buy);
  const s = Number(q.sell);
  if (!b || !s) return null;
  return (s - b) / ((s + b) / 2);
}

function isReference(q: Quote): boolean {
  return q.kind === "market_reference";
}

function RateCell({ q, value }: { q: Quote; value: string | null }) {
  const ref = isReference(q);
  return (
    <span className={cn("tnum", ref && "text-muted")}>
      {ref && value !== null && <span aria-hidden>≈ </span>}
      {ref && value !== null && <span className="sr-only">aproximadamente </span>}
      {formatRateFixed(value, q.quote, { reference: ref })}
    </span>
  );
}

export function QuoteTable({ quotes, sources, onSelect, selectedId, compact = false, caption, emptyKind = "no-match" }: { quotes: Quote[]; sources: Source[]; onSelect?: (q: Quote) => void; selectedId?: string | null; compact?: boolean; caption?: string; emptyKind?: "no-match" | "no-data" }) {
  const [sorting, setSorting] = React.useState<SortingState>([{ id: "source", desc: false }]);
  const srcName = React.useCallback((id: string) => sources.find((s) => s.id === id)?.name ?? id, [sources]);
  // País pela cobertura (ME3): fonte paraguaia ganha a bandeira PY; sem país não há bandeira (nunca quebra).
  const countryOf = React.useCallback((id: string) => {
    const s = sources.find((x) => x.id === id);
    return s ? sourceCountry(s) : null;
  }, [sources]);
  const columns = React.useMemo(
    () => [
      col.accessor((q) => srcName(q.source_id), {
        id: "source",
        header: "Fonte",
        cell: (c) => (
          <span className="inline-flex items-center gap-1.5 font-medium">
            {isReference(c.row.original) && <Landmark className="size-3 text-muted" aria-hidden />}
            {countryOf(c.row.original.source_id) === "PY" && (
              <>
                <FlagIcon country="PY" />
                <span className="sr-only">Paraguai, </span>
              </>
            )}
            {c.getValue()}
          </span>
        ),
      }),
      col.accessor((q) => (isReference(q) ? "—" : q.city ? CITY_LABEL[q.city] : "Digital"), {
        id: "city",
        header: "Local",
        cell: (c) => <span className={cn(!c.row.original.city && "text-muted")}>{c.getValue()}</span>,
      }),
      col.accessor((q) => `${q.base}/${q.quote}`, { id: "pair", header: "Par", cell: (c) => <span className="tnum">{c.getValue()}</span> }),
      col.accessor((q) => (q.buy === null ? null : Number(q.buy)), {
        id: "buy",
        header: "Compra",
        cell: (c) => <RateCell q={c.row.original} value={c.row.original.buy} />,
      }),
      col.accessor((q) => (q.sell === null ? null : Number(q.sell)), {
        id: "sell",
        header: "Venda",
        cell: (c) => <RateCell q={c.row.original} value={c.row.original.sell} />,
      }),
      col.accessor((q) => spreadRatio(q), {
        id: "spread",
        header: "Spread",
        cell: (c) => <span className="tnum text-muted">{formatPercent(c.getValue())}</span>,
      }),
      col.accessor((q) => q.modality, { id: "modality", header: "Modalidade", cell: (c) => <Badge variant="outline">{MODALITY_LABEL[c.getValue()]}</Badge> }),
      col.accessor((q) => q.kind, {
        id: "kind",
        header: "Tipo",
        cell: (c) => (c.getValue() === "executable" ? <Badge variant="gain">Executável</Badge> : c.getValue() === "market_reference" ? <Badge variant="reference">Referência</Badge> : <Badge variant="default">Indicativa</Badge>),
      }),
      col.accessor((q) => Date.parse(q.captured_at), {
        id: "age",
        header: "Idade",
        cell: (c) => <AgeCell iso={c.row.original.captured_at} declared={c.row.original.declared_updated_at} />,
      }),
    ],
    [srcName, countryOf],
  );
  const columnVisibility = compact ? COMPACT_HIDDEN : ALL_VISIBLE;
  // eslint-disable-next-line react-hooks/incompatible-library -- TanStack Table gerencia a própria memoização
  const table = useReactTable({ data: quotes, columns, state: { sorting, columnVisibility }, onSortingChange: setSorting, getCoreRowModel: getCoreRowModel(), getSortedRowModel: getSortedRowModel() });
  const rows = table.getRowModel().rows;

  if (rows.length === 0) return <EmptyState kind={emptyKind} compact title={emptyKind === "no-data" ? "Nenhuma cotação coletada ainda" : "Nenhuma cotação para os filtros atuais"} />;

  return (
    <Table scrollLabel="Tabela de cotações (rola para o lado)">
      {caption && <TableCaption>{caption}</TableCaption>}
      <TableHeader>
        {table.getHeaderGroups().map((hg) => (
          <TableRow key={hg.id} className="hover:bg-transparent">
            {hg.headers.map((h) => (
              <TableHead key={h.id} className={cn(RIGHT.has(h.id) && "text-right", h.id === "source" && "sticky left-0 z-10 bg-surface")} aria-sort={h.column.getIsSorted() === "asc" ? "ascending" : h.column.getIsSorted() === "desc" ? "descending" : "none"}>
                <button type="button" className="inline-flex items-center gap-1 hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring" onClick={h.column.getToggleSortingHandler()}>
                  {flexRender(h.column.columnDef.header, h.getContext())}
                  <ArrowUpDown className="size-3 opacity-50" aria-hidden />
                </button>
              </TableHead>
            ))}
          </TableRow>
        ))}
      </TableHeader>
      <TableBody>
        {rows.map((row) => (
          <TableRow
            key={row.id}
            data-state={selectedId === row.original.id ? "selected" : undefined}
            className={cn(onSelect && "cursor-pointer", isReference(row.original) && "border-dashed")}
            onClick={() => onSelect?.(row.original)}
            onKeyDown={(e) => { if (onSelect && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); onSelect(row.original); } }}
            tabIndex={onSelect ? 0 : undefined}
            aria-selected={onSelect ? selectedId === row.original.id : undefined}
          >
            {row.getVisibleCells().map((cell) => (
              <TableCell key={cell.id} className={cn(RIGHT.has(cell.column.id) && "text-right", cell.column.id === "source" && "sticky left-0 z-10 bg-surface")}>
                {flexRender(cell.column.columnDef.cell, cell.getContext())}
              </TableCell>
            ))}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

export function AgeCell({ iso, declared }: { iso: string; declared?: string | null }) {
  const now = useNow();
  if (now === 0) return <span className="tnum text-muted">…</span>;
  const s = ageSeconds(iso, now) ?? 0;
  const stale = s > 1800;
  return (
    <time dateTime={iso} data-volatile className={cn("tnum", stale ? "text-warn" : "text-muted")} title={declared ? `Atualização declarada pela fonte: ${new Date(declared).toLocaleString("pt-BR")}` : undefined}>
      {stale && <span className="sr-only">cotação antiga: </span>}
      {formatAge(iso, now)}
      {stale && <span aria-hidden> ⚠</span>}
    </time>
  );
}
