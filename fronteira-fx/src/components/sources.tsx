"use client";
import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import { Copy } from "lucide-react";
import { useEvidence, useSources } from "@/lib/queries";
import { api } from "@/lib/api/client";
import { useSettings } from "@/lib/settings";
import { PageHeader } from "@/components/shell/page-header";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { HEALTH_LABEL, HEALTH_TONE } from "@/components/ui/labels";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { TableSkeleton } from "@/components/ui/table-skeleton";
import { ErrorState } from "@/components/ui/error-state";
import { EmptyState } from "@/components/ui/empty-state";
import { formatAge, formatDateTime } from "@/lib/format";
import { CITY_LABEL, type Evidence } from "@/lib/api/types";
import { Skeleton } from "@/components/ui/skeleton";
import { useNow } from "@/lib/use-now";
import { cn } from "@/lib/utils";

const METHOD: Record<string, string> = { official_api: "API oficial", html: "Coletor HTTP/HTML", browser: "Navegador automatizado", manual: "Registro manual" };

export function Sources() {
  return (
    <React.Suspense fallback={<Skeleton className="h-40" />}>
      <SourcesInner />
    </React.Suspense>
  );
}

function SourcesInner() {
  const { mode } = useSettings();
  const now = useNow();
  const sourcesQ = useSources();
  const sources = sourcesQ.data ?? [];
  const [sel, setSel] = React.useState<string | undefined>(undefined);
  const ev = useEvidence(sel);
  const params = useSearchParams();
  const highlight = params.get("evidence");
  const inList = !!highlight && (ev.data ?? []).some((e) => e.id === highlight);
  // Evidência destacada pela URL que não está na página atual: busca por id (GET /v1/evidence/{id}).
  const single = useQuery({ queryKey: ["evidence-by-id", mode, highlight], queryFn: () => api.evidenceById(mode, highlight!), enabled: !!highlight && !!ev.data && !inList, retry: false });
  const rows: Evidence[] = React.useMemo(() => {
    const list = ev.data ?? [];
    return single.data && !list.some((e) => e.id === single.data!.id) ? [single.data, ...list] : list;
  }, [ev.data, single.data]);
  return (
    <div className="space-y-4">
      <PageHeader title="Fontes" description="Cobertura, capacidades comprovadas, limitações e saúde de cada adaptador. Consultas bloqueadas ou dependentes de sessão retornam estado explícito." />
      {sourcesQ.isLoading && <TableSkeleton rows={3} cols={3} />}
      {sourcesQ.isError && <ErrorState title="As fontes não carregaram" error={sourcesQ.error} onRetry={() => void sourcesQ.refetch()} />}
      {sourcesQ.data && sources.length === 0 && <EmptyState kind="no-data" title="Nenhuma fonte cadastrada" description="Os adaptadores do backend aparecem aqui assim que forem registrados." />}
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {sources.map((s) => (
          <Card key={s.id} className={sel === s.id ? "ring-2 ring-ring" : undefined} data-testid="source-card">
            <CardHeader>
              <div className="flex items-start justify-between gap-2">
                <div>
                  <CardTitle>{s.name}</CardTitle>
                  <CardDescription>{METHOD[s.method]} · sondada a cada {Math.max(1, Math.round(s.poll_interval_s / 60))} min</CardDescription>
                </div>
                <Badge variant={HEALTH_TONE[s.health] ?? "outline"}>{HEALTH_LABEL[s.health] ?? s.health}</Badge>
              </div>
            </CardHeader>
            <CardContent className="space-y-2 text-xs">
              <p className="text-muted">
                Última coleta OK: <span className="tnum text-foreground" data-volatile>{now === 0 ? "…" : formatAge(s.last_success_at, now)}</span>
                {s.last_error && <span className="block text-loss">Erro: {s.last_error}</span>}
              </p>
              <p><span className="text-muted">Cobertura:</span> {s.coverage.cities.length ? s.coverage.cities.map((c) => CITY_LABEL[c]).join(", ") : "digital"} · {s.coverage.currencies.join("/")}</p>
              <div className="flex flex-wrap gap-1">{s.capabilities.length ? s.capabilities.map((c) => <Badge key={c} variant="accent">{c}</Badge>) : <Badge variant="outline">nenhuma capacidade comprovada</Badge>}</div>
              <ul className="list-disc pl-4 text-muted">{s.limitations.map((l) => <li key={l}>{l}</li>)}</ul>
              <div className="flex items-center justify-between pt-1">
                <a className="text-accent underline" href={s.url} target="_blank" rel="noreferrer noopener">site<span className="sr-only"> de {s.name} (abre em nova aba)</span></a>
                <button type="button" className="rounded-sm text-accent underline focus-visible:outline-2 focus-visible:outline-ring" onClick={() => setSel(sel === s.id ? undefined : s.id)} aria-pressed={sel === s.id}>
                  {sel === s.id ? "todas as evidências" : "ver evidências"}
                </button>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
      <Card data-testid="evidence-card">
        <CardHeader><CardTitle>Evidências {sel ? `· ${sources.find((s) => s.id === sel)?.name}` : ""}</CardTitle><CardDescription>Cada cotação aponta para a captura (hash, trecho e regras de parser) que a gerou. Resultado financeiro deve ser reproduzível a partir daqui.</CardDescription></CardHeader>
        <CardContent className="p-0 sm:p-2">
          {ev.isLoading && <TableSkeleton rows={5} cols={6} />}
          {ev.isError && <ErrorState title="As evidências não carregaram" error={ev.error} onRetry={() => void ev.refetch()} />}
          {single.isError && highlight && <p role="alert" className="p-3 text-xs text-loss">A evidência «{highlight}» não foi encontrada.</p>}
          {ev.data && rows.length === 0 && <EmptyState kind="no-data" compact title="Nenhuma evidência registrada" description="As capturas aparecem aqui a cada coleta bem-sucedida." />}
          {ev.data && rows.length > 0 && (
            <Table scrollLabel="Evidências das capturas (rola para o lado)">
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead>ID</TableHead>
                  <TableHead>Fonte</TableHead>
                  <TableHead>Tipo</TableHead>
                  <TableHead>Capturado</TableHead>
                  <TableHead>Trecho</TableHead>
                  <TableHead>Regras</TableHead>
                  <TableHead>SHA-256</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((e) => (
                  <TableRow key={e.id} className={cn(highlight === e.id && "bg-accent/10")} id={`ev-${e.id}`} data-testid="evidence-row" data-highlight={highlight === e.id ? "true" : undefined}>
                    <TableCell className="tnum text-xs">{e.id}</TableCell>
                    <TableCell>{sources.find((s) => s.id === e.source_id)?.name ?? e.source_id}</TableCell>
                    <TableCell><Badge variant="outline">{e.kind}</Badge></TableCell>
                    <TableCell className="tnum text-xs"><time dateTime={e.captured_at}>{formatDateTime(e.captured_at)}</time></TableCell>
                    <TableCell className="max-w-md truncate text-xs">{e.excerpt}</TableCell>
                    <TableCell className="text-xs text-muted">{e.rules.join(", ")}</TableCell>
                    <TableCell className="text-xs text-muted"><HashDialog evidence={e} /></TableCell>
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

/** Hash completo num diálogo com «Copiar» (o `title=` não aparece no toque). */
function HashDialog({ evidence: e }: { evidence: Evidence }) {
  const [copied, setCopied] = React.useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(e.sha256);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  };
  return (
    <Dialog onOpenChange={() => setCopied(false)}>
      <DialogTrigger asChild>
        <button type="button" className="tnum rounded-sm underline decoration-dotted focus-visible:outline-2 focus-visible:outline-ring" aria-label={`Ver hash completo da evidência ${e.id}`}>{e.sha256.slice(0, 12)}…</button>
      </DialogTrigger>
      <DialogContent className="max-w-lg">
        <DialogHeader><DialogTitle>Evidência {e.id}</DialogTitle><DialogDescription>{e.kind} · capturada em {formatDateTime(e.captured_at)} · <a className="text-accent underline" href={e.url} target="_blank" rel="noreferrer noopener">origem</a></DialogDescription></DialogHeader>
        <p className="text-xs text-muted">SHA-256 do conteúdo capturado</p>
        <p className="tnum break-all rounded-md border border-border bg-surface-2 p-2 text-xs">{e.sha256}</p>
        <div className="flex items-center gap-2">
          <Button type="button" size="sm" variant="secondary" onClick={copy}><Copy aria-hidden /> Copiar hash</Button>
          <output aria-live="polite" className="text-xs text-muted">{copied ? "copiado" : ""}</output>
        </div>
        {e.excerpt && <p className="text-xs"><span className="text-muted">Trecho:</span> {e.excerpt}</p>}
      </DialogContent>
    </Dialog>
  );
}
