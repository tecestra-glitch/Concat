"use client";
import * as React from "react";
import { useEvidence, useSources } from "@/lib/queries";
import { PageHeader } from "@/components/shell/page-header";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { formatAge, formatDateTime } from "@/lib/format";
import { CITY_LABEL } from "@/lib/api/types";
import { Skeleton } from "@/components/ui/skeleton";
import { useSearchParams } from "next/navigation";

const METHOD: Record<string, string> = { official_api: "API oficial", html: "Coletor HTTP/HTML", browser: "Navegador automatizado", manual: "Registro manual" };
const tone: Record<string, "gain" | "warn" | "loss" | "outline"> = { ok: "gain", degraded: "warn", stale: "warn", blocked: "loss", unknown: "outline" };

export function Sources() {
  return (
    <React.Suspense fallback={<Skeleton className="h-40" />}>
      <SourcesInner />
    </React.Suspense>
  );
}

function SourcesInner() {
  const { data: sources = [], isLoading } = useSources();
  const [sel, setSel] = React.useState<string | undefined>(undefined);
  const ev = useEvidence(sel);
  const params = useSearchParams();
  const highlight = params.get("evidence");
  return (
    <div className="space-y-4">
      <PageHeader title="Fontes" description="Cobertura, capacidades comprovadas, limitações e saúde de cada adaptador. Consultas bloqueadas ou dependentes de sessão retornam estado explícito." />
      {isLoading && <Skeleton className="h-40" />}
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {sources.map((s) => (
          <Card key={s.id} className={sel === s.id ? "ring-2 ring-ring" : undefined}>
            <CardHeader>
              <div className="flex items-start justify-between gap-2">
                <div>
                  <CardTitle>{s.name}</CardTitle>
                  <CardDescription>{METHOD[s.method]} · a cada {Math.round(s.poll_interval_s / 60)} min</CardDescription>
                </div>
                <Badge variant={tone[s.health]}>{s.health}</Badge>
              </div>
            </CardHeader>
            <CardContent className="space-y-2 text-xs">
              <p className="text-muted">Última coleta OK: <span className="tnum text-foreground">{formatAge(s.last_success_at)}</span>{s.last_error && <span className="block text-loss">Erro: {s.last_error}</span>}</p>
              <p><span className="text-muted">Cobertura:</span> {s.coverage.cities.length ? s.coverage.cities.map((c) => CITY_LABEL[c]).join(", ") : "digital"} · {s.coverage.currencies.join("/")}</p>
              <div className="flex flex-wrap gap-1">{s.capabilities.length ? s.capabilities.map((c) => <Badge key={c} variant="accent">{c}</Badge>) : <Badge variant="outline">nenhuma capacidade comprovada</Badge>}</div>
              <ul className="list-disc pl-4 text-muted">{s.limitations.map((l) => <li key={l}>{l}</li>)}</ul>
              <div className="flex items-center justify-between pt-1">
                <a className="text-accent underline" href={s.url} target="_blank" rel="noreferrer noopener">site</a>
                <button type="button" className="rounded-sm text-accent underline focus-visible:outline-2 focus-visible:outline-ring" onClick={() => setSel(sel === s.id ? undefined : s.id)} aria-pressed={sel === s.id}>
                  {sel === s.id ? "todas as evidências" : "ver evidências"}
                </button>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
      <Card>
        <CardHeader><CardTitle>Evidências {sel ? `· ${sources.find((s) => s.id === sel)?.name}` : ""}</CardTitle><CardDescription>Cada cotação aponta para a captura (hash, trecho e regras de parser) que a gerou. Resultado financeiro deve ser reproduzível a partir daqui.</CardDescription></CardHeader>
        <CardContent className="p-0 sm:p-2">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="border-b border-border text-left text-[11px] uppercase tracking-wide text-muted"><th className="px-2 py-2">ID</th><th className="px-2 py-2">Fonte</th><th className="px-2 py-2">Tipo</th><th className="px-2 py-2">Capturado</th><th className="px-2 py-2">Trecho</th><th className="px-2 py-2">Regras</th><th className="px-2 py-2">SHA-256</th></tr></thead>
              <tbody>
                {(ev.data ?? []).map((e) => (
                  <tr key={e.id} className={`border-b border-border ${highlight === e.id ? "bg-accent/10" : ""}`} id={`ev-${e.id}`}>
                    <td className="tnum px-2 py-1.5 text-xs">{e.id}</td>
                    <td className="px-2 py-1.5">{e.source_id}</td>
                    <td className="px-2 py-1.5"><Badge variant="outline">{e.kind}</Badge></td>
                    <td className="tnum px-2 py-1.5 text-xs">{formatDateTime(e.captured_at)}</td>
                    <td className="max-w-md truncate px-2 py-1.5 text-xs" title={e.excerpt}>{e.excerpt}</td>
                    <td className="px-2 py-1.5 text-xs text-muted">{e.rules.join(", ")}</td>
                    <td className="tnum max-w-[8rem] truncate px-2 py-1.5 text-xs text-muted" title={e.sha256}>{e.sha256.slice(0, 12)}…</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
