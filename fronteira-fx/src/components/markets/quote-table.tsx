"use client";
import * as React from "react";
import { createColumnHelper, flexRender, getCoreRowModel, getSortedRowModel, useReactTable, type SortingState } from "@tanstack/react-table";
import { ArrowUpDown } from "lucide-react";
import type { Quote, Source } from "@/lib/api/types";
import { CITY_LABEL, MODALITY_LABEL } from "@/lib/api/types";
import { formatAge, formatRate, ageSeconds } from "@/lib/format";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { useNow } from "@/lib/use-now";

const col = createColumnHelper<Quote>();

export function spreadPct(q: Quote): number | null {
  if (q.buy === null || q.sell === null) return null;
  const b = Number(q.buy);
  const s = Number(q.sell);
  if (!b || !s) return null;
  return ((s - b) / ((s + b) / 2)) * 100;
}

export function QuoteTable({ quotes, sources, onSelect, selectedId, compact = false }: { quotes: Quote[]; sources: Source[]; onSelect?: (q: Quote) => void; selectedId?: string | null; compact?: boolean }) {
  const [sorting, setSorting] = React.useState<SortingState>([{ id: "source", desc: false }]);
  const srcName = React.useCallback((id: string) => sources.find((s) => s.id === id)?.name ?? id, [sources]);
  const columns = React.useMemo(
    () => [
      col.accessor((q) => srcName(q.source_id), { id: "source", header: "Fonte", cell: (c) => <span className="font-medium">{c.getValue()}</span> }),
      col.accessor((q) => (q.city ? CITY_LABEL[q.city] : "Digital"), {
        id: "city",
        header: "Local",
        cell: (c) => <span className={cn(c.row.original.city ? "" : "text-accent")}>{c.getValue()}</span>,
      }),
      col.accessor((q) => `${q.base}/${q.quote}`, { id: "pair", header: "Par", cell: (c) => <span className="tnum">{c.getValue()}</span> }),
      col.accessor((q) => (q.buy === null ? null : Number(q.buy)), {
        id: "buy",
        header: () => <span className="text-gain">Compra</span>,
        cell: (c) => <span className="tnum text-gain">{formatRate(c.getValue(), c.row.original.quote)}</span>,
      }),
      col.accessor((q) => (q.sell === null ? null : Number(q.sell)), {
        id: "sell",
        header: () => <span className="text-loss">Venda</span>,
        cell: (c) => <span className="tnum text-loss">{formatRate(c.getValue(), c.row.original.quote)}</span>,
      }),
      col.accessor((q) => spreadPct(q), {
        id: "spread",
        header: "Spread",
        cell: (c) => <span className="tnum text-muted">{c.getValue() === null ? "—" : `${c.getValue()!.toFixed(2).replace(".", ",")} %`}</span>,
      }),
      col.accessor((q) => q.modality, { id: "modality", header: "Modalidade", cell: (c) => <Badge variant="outline">{MODALITY_LABEL[c.getValue()]}</Badge> }),
      col.accessor((q) => q.kind, {
        id: "kind",
        header: "Tipo",
        cell: (c) => <Badge variant={c.getValue() === "executable" ? "gain" : c.getValue() === "market_reference" ? "accent" : "default"}>{c.getValue() === "executable" ? "Executável" : c.getValue() === "market_reference" ? "Referência" : "Indicativa"}</Badge>,
      }),
      col.accessor((q) => Date.parse(q.captured_at), {
        id: "age",
        header: "Idade",
        cell: (c) => <AgeCell iso={c.row.original.captured_at} declared={c.row.original.declared_updated_at} />,
      }),
    ],
    [srcName],
  );
  const table = useReactTable({ data: quotes, columns, state: { sorting }, onSortingChange: setSorting, getCoreRowModel: getCoreRowModel(), getSortedRowModel: getSortedRowModel() });
  const hidden = compact ? new Set(["spread", "modality", "kind"]) : new Set<string>();

  return (
    <Table>
      <TableHeader>
        {table.getHeaderGroups().map((hg) => (
          <TableRow key={hg.id} className="hover:bg-transparent">
            {hg.headers.filter((h) => !hidden.has(h.id)).map((h) => (
              <TableHead key={h.id} className={cn(["buy", "sell", "spread", "age"].includes(h.id) && "text-right")} aria-sort={h.column.getIsSorted() === "asc" ? "ascending" : h.column.getIsSorted() === "desc" ? "descending" : "none"}>
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
        {table.getRowModel().rows.length === 0 && (
          <TableRow><TableCell colSpan={9} className="py-6 text-center text-muted">Nenhuma cotação para os filtros atuais.</TableCell></TableRow>
        )}
        {table.getRowModel().rows.map((row) => (
          <TableRow
            key={row.id}
            data-state={selectedId === row.original.id ? "selected" : undefined}
            className={cn(onSelect && "cursor-pointer")}
            onClick={() => onSelect?.(row.original)}
            onKeyDown={(e) => { if (onSelect && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); onSelect(row.original); } }}
            tabIndex={onSelect ? 0 : undefined}
            aria-selected={onSelect ? selectedId === row.original.id : undefined}
          >
            {row.getVisibleCells().filter((c) => !hidden.has(c.column.id)).map((cell) => (
              <TableCell key={cell.id} className={cn(["buy", "sell", "spread", "age"].includes(cell.column.id) && "text-right")}>
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
    <span className={cn("tnum", stale ? "text-warn" : "text-muted")} title={declared ? `Atualização declarada pela fonte: ${new Date(declared).toLocaleString("pt-BR")}` : undefined}>
      {stale && <span className="sr-only">cotação antiga: </span>}
      {formatAge(iso, now)}
      {stale && <span aria-hidden> ⚠</span>}
    </span>
  );
}
