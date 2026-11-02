"use client";
import * as React from "react";
import Link from "next/link";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Label } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { formatAge, formatDateTime } from "@/lib/format";
import { CHANGE_KIND_LABEL, CHANGE_KIND_TONE, formatClock, type ChangeKind } from "@/lib/api/watch";
import type { Source } from "@/lib/api/types";
import { useChanges } from "./use-watch";
import { useTicker } from "./use-ticker";

const LIMIT = 60;

export function ChangeTimeline({ sources, names }: { sources: Source[]; names: Record<string, string> }) {
  const [source, setSource] = React.useState("all");
  const [kind, setKind] = React.useState("all");
  const q = useChanges({ source, kind });
  const now = useTicker();
  const all = q.data ?? [];
  const items = all.slice(0, LIMIT);
  return (
    <Card data-testid="change-timeline">
      <CardHeader className="gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <CardTitle>Linha do tempo de mudanças</CardTitle>
          <CardDescription>Só mudanças reais entram aqui (o hash do conteúdo relevante mudou): cotação, layout da página ou estado da fonte, sempre com a evidência da captura.</CardDescription>
        </div>
        <div className="grid grid-cols-2 gap-2 sm:flex" role="group" aria-label="Filtros da linha do tempo">
          <div className="flex flex-col gap-1">
            <Label htmlFor="tl-source">Fonte</Label>
            <Select value={source} onValueChange={setSource}>
              <SelectTrigger id="tl-source" className="sm:w-44"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todas</SelectItem>
                {sources.map((s) => <SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="tl-kind">Tipo</Label>
            <Select value={kind} onValueChange={setKind}>
              <SelectTrigger id="tl-kind" className="sm:w-36"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todos</SelectItem>
                {(Object.keys(CHANGE_KIND_LABEL) as ChangeKind[]).map((k) => <SelectItem key={k} value={k}>{CHANGE_KIND_LABEL[k]}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {q.isLoading && <Skeleton className="h-32" />}
        {q.isError && <p role="alert" className="text-sm text-loss">Falha ao carregar mudanças: {(q.error as Error).message}</p>}
        {!q.isLoading && !q.isError && items.length === 0 && <p className="py-6 text-center text-sm text-muted">Nenhuma mudança para os filtros atuais.</p>}
        <ol aria-live="polite" aria-relevant="additions" aria-label="Mudanças detectadas" className="divide-y divide-border">
          {items.map((c) => (
            <li key={c.id} className="grid gap-x-4 gap-y-1 py-2.5 text-sm sm:grid-cols-[9.5rem_1fr_auto] sm:items-start">
              <time dateTime={c.ts} title={formatDateTime(c.ts)} className="tnum text-xs text-muted">
                {formatClock(c.ts)} <span aria-hidden>·</span> {now === 0 ? "…" : formatAge(c.ts, now)}
              </time>
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">{names[c.source_id] ?? c.source_id}</span>
                  <Badge variant={CHANGE_KIND_TONE[c.kind] ?? "outline"}>{CHANGE_KIND_LABEL[c.kind] ?? c.kind}</Badge>
                </div>
                <p className="break-words text-foreground/90">{c.summary}</p>
              </div>
              {c.evidence_id ? (
                <Link href={`/fontes?evidence=${encodeURIComponent(c.evidence_id)}`} className="text-xs text-accent underline focus-visible:outline-2 focus-visible:outline-ring">
                  evidência<span className="sr-only"> da mudança em {names[c.source_id] ?? c.source_id}</span>
                </Link>
              ) : (
                <span className="text-xs text-muted">sem evidência</span>
              )}
            </li>
          ))}
        </ol>
        {all.length > LIMIT && <p className="pt-2 text-[11px] text-muted">Mostrando {LIMIT} de {all.length} mudanças.</p>}
      </CardContent>
    </Card>
  );
}
