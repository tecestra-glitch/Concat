"use client";
/** U8 — memória do agente (módulo memory): resumo via api.memorySummary e lista filtrável (GET /v1/memory). */
import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { PageHeader } from "@/components/shell/page-header";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { TableSkeleton } from "@/components/ui/table-skeleton";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/ui/error-state";
import { EmptyState } from "@/components/ui/empty-state";
import { useSettings } from "@/lib/settings";
import { useMemorySummary } from "@/lib/queries";
import { formatDateTime } from "@/lib/format";
import { listMemory, type MemoryQuery } from "@/components/knowledge/knowledge-api";

const KINDS = ["all", "preference", "decision", "fact", "outcome"] as const;
const KIND_LABEL: Record<string, string> = { all: "Todos", preference: "Preferência", decision: "Decisão", fact: "Fato", outcome: "Resultado" };

export function MemoryPage() {
  const { mode } = useSettings();
  const [filters, setFilters] = React.useState<MemoryQuery>({ q: "", kind: "all", tag: "", limit: 50 });
  const summary = useMemorySummary(20);
  const list = useQuery({ queryKey: ["memory", mode, filters], queryFn: () => listMemory(mode, filters), staleTime: 30_000 });

  return (
    <div className="space-y-4">
      <PageHeader title="Memória" description="O que o agente guardou: preferências, decisões, fatos e resultados. Nada aqui é cotação nem cálculo." />
      <Card data-testid="memory-summary">
        <CardHeader>
          <CardTitle>Resumo</CardTitle>
          <CardDescription>Síntese das memórias mais recentes.</CardDescription>
        </CardHeader>
        <CardContent>
          {summary.isLoading && <Skeleton className="h-10" />}
          {summary.isError && <ErrorState compact title="O resumo não carregou" error={summary.error} onRetry={() => void summary.refetch()} />}
          {summary.data && <p className="text-sm leading-6">{summary.data.summary || "Sem memórias registradas ainda."}</p>}
        </CardContent>
      </Card>
      <Card data-testid="memory-list">
        <CardHeader className="gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <CardTitle>Memórias</CardTitle>
            <CardDescription>Mais recentes primeiro; busca textual e filtro por tipo e etiqueta.</CardDescription>
          </div>
          <div className="grid grid-cols-2 gap-2 sm:flex" role="group" aria-label="Filtros da memória">
            <div className="grid gap-1 col-span-2 sm:col-span-1">
              <Label htmlFor="mem-q">Buscar</Label>
              <Input id="mem-q" value={filters.q} onChange={(e) => setFilters({ ...filters, q: e.target.value })} placeholder="texto" className="sm:w-44" autoComplete="off" />
            </div>
            <div className="grid gap-1">
              <Label htmlFor="mem-kind">Tipo</Label>
              <select id="mem-kind" className="h-9 rounded-md border border-border bg-background px-2 text-sm" value={filters.kind} onChange={(e) => setFilters({ ...filters, kind: e.target.value })}>
                {KINDS.map((k) => <option key={k} value={k}>{KIND_LABEL[k]}</option>)}
              </select>
            </div>
            <div className="grid gap-1">
              <Label htmlFor="mem-tag">Etiqueta</Label>
              <Input id="mem-tag" value={filters.tag} onChange={(e) => setFilters({ ...filters, tag: e.target.value })} placeholder="ex.: ueno" className="sm:w-32" autoComplete="off" />
            </div>
          </div>
        </CardHeader>
        <CardContent className="p-0 sm:p-2">
          {mode === "demo" && <EmptyState kind="no-data" title="Sem memórias na demonstração" description="A memória vive no backend real; em modo demonstração nada é lido nem gravado." />}
          {mode !== "demo" && list.isLoading && <TableSkeleton rows={4} cols={4} />}
          {mode !== "demo" && list.isError && <ErrorState title="A lista de memórias falhou" error={list.error} onRetry={() => void list.refetch()} />}
          {mode !== "demo" && list.data && list.data.length === 0 && <EmptyState kind={filters.q || filters.tag || filters.kind !== "all" ? "no-match" : "no-data"} title={filters.q || filters.tag || filters.kind !== "all" ? "Nenhuma memória para estes filtros" : "Nenhuma memória registrada"} description="O agente grava aqui o que aprende nas conversas e operações." />}
          {mode !== "demo" && list.data && list.data.length > 0 && (
            <Table scrollLabel="Memórias do agente">
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead>Quando</TableHead>
                  <TableHead>Tipo</TableHead>
                  <TableHead>Texto</TableHead>
                  <TableHead>Etiquetas</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {list.data.map((m) => (
                  <TableRow key={m.id}>
                    <TableCell className="tnum whitespace-nowrap text-xs text-muted"><time dateTime={m.created_at}>{formatDateTime(m.created_at)}</time></TableCell>
                    <TableCell><Badge variant="outline">{KIND_LABEL[m.kind] ?? m.kind}</Badge></TableCell>
                    <TableCell className="max-w-lg text-sm">{m.text}</TableCell>
                    <TableCell className="text-xs"><div className="flex flex-wrap gap-1">{m.tags.map((t) => <Badge key={t} variant="default">{t}</Badge>)}</div></TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
