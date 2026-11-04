"use client";
/**
 * U8 — busca de conhecimento (módulo rag). Só documentação, tarifas, horários e evidências:
 * cotações e cálculos nunca vêm daqui (regra do projeto). Nada além do que o contrato oferece.
 */
import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { PageHeader } from "@/components/shell/page-header";
import { Card, CardContent } from "@/components/ui/card";
import { Input, Label } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { TableSkeleton } from "@/components/ui/table-skeleton";
import { ErrorState } from "@/components/ui/error-state";
import { EmptyState } from "@/components/ui/empty-state";
import { useSettings } from "@/lib/settings";
import { api } from "@/lib/api/client";
import type { KnowledgeQuery } from "@/lib/api/types";

const K_OPTIONS = [5, 10, 20];

export function KnowledgeSearch() {
  const { mode } = useSettings();
  const [draft, setDraft] = React.useState<KnowledgeQuery>({ q: "", k: 5, tag: "" });
  const [query, setQuery] = React.useState<KnowledgeQuery | null>(null);
  const res = useQuery({ queryKey: ["rag-search", mode, query], queryFn: () => api.searchKnowledge(mode, query!), enabled: !!query && query.q.trim().length > 0, staleTime: 60_000 });

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!draft.q.trim()) return;
    setQuery({ ...draft, q: draft.q.trim() });
  };

  return (
    <div className="space-y-4">
      <PageHeader title="Conhecimento" description="Busca na base de documentação, tarifas, horários e evidências das fontes. Cotações e cálculos não saem daqui: vêm dos adaptadores e do motor." />
      <Card>
        <CardContent className="pt-4">
          <form onSubmit={submit} className="grid gap-3 sm:grid-cols-[1fr_8rem_8rem_auto] sm:items-end" role="search">
            <div className="grid gap-1">
              <Label htmlFor="rag-q">Pergunta ou termo</Label>
              <Input id="rag-q" value={draft.q} onChange={(e) => setDraft({ ...draft, q: e.target.value })} placeholder="Ex.: tarifa de saque em caixa" autoComplete="off" />
            </div>
            <div className="grid gap-1">
              <Label htmlFor="rag-tag">Etiqueta</Label>
              <Input id="rag-tag" value={draft.tag} onChange={(e) => setDraft({ ...draft, tag: e.target.value })} placeholder="opcional" autoComplete="off" />
            </div>
            <div className="grid gap-1">
              <Label htmlFor="rag-k">Resultados</Label>
              <select id="rag-k" className="h-9 rounded-control border border-control-border bg-surface px-2 text-body" value={draft.k} onChange={(e) => setDraft({ ...draft, k: Number(e.target.value) })}>
                {K_OPTIONS.map((k) => <option key={k} value={k}>{k}</option>)}
              </select>
            </div>
            <Button type="submit" disabled={!draft.q.trim() || res.isFetching}><Search aria-hidden /> {res.isFetching ? "Buscando…" : "Buscar"}</Button>
          </form>
        </CardContent>
      </Card>
      <Card data-testid="knowledge-results">
        <CardContent className="p-0 sm:p-2">
          {!query && <EmptyState kind="no-data" title="Digite um termo para buscar" description="A busca é léxica sobre os documentos cadastrados (tarifas, horários, regras das fontes)." />}
          {query && mode === "demo" && <EmptyState kind="no-data" title="Sem base de conhecimento na demonstração" description="A busca consulta o backend real; em modo demonstração nada é pesquisado nem enviado." />}
          {query && mode !== "demo" && res.isLoading && <TableSkeleton rows={4} cols={3} />}
          {query && mode !== "demo" && res.isError && <ErrorState title="A busca falhou" error={res.error} onRetry={() => void res.refetch()} />}
          {query && mode !== "demo" && res.data && res.data.length === 0 && <EmptyState kind="no-match" title={`Nada encontrado para «${query.q}»`} description="Tente outro termo ou remova a etiqueta." />}
          {query && mode !== "demo" && res.data && res.data.length > 0 && (
            <Table scrollLabel="Resultados da busca de conhecimento">
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead>Documento</TableHead>
                  <TableHead>Trecho</TableHead>
                  <TableHead>Fonte</TableHead>
                  <TableHead className="text-right">Relevância</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {res.data.map((hit) => (
                  <TableRow key={hit.id}>
                    <TableCell className="font-medium">{hit.title}</TableCell>
                    <TableCell className="max-w-md text-xs text-foreground/90">{hit.snippet}</TableCell>
                    <TableCell className="text-xs">
                      <div className="flex flex-wrap gap-1">
                        <span>{hit.source}</span>
                        {hit.tags.map((t) => <Badge key={t} variant="outline">{t}</Badge>)}
                      </div>
                    </TableCell>
                    <TableCell className="tnum text-right text-xs text-muted">{Number(hit.score).toLocaleString("pt-BR", { maximumFractionDigits: 3 })}</TableCell>
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
