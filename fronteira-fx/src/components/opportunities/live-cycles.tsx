"use client";
/**
 * Cruzamento ao vivo: ciclos lucrativos no grafo de posições (moeda@conta) a partir do saldo já
 * estacionado. Todos os modos passam por `useCycles` → `api.cycles(mode)` (D1: valores em string
 * decimal; demo roda o espelho TS do motor, real/simulação chamam GET /v1/opportunities/cycles).
 */
import * as React from "react";
import { ArrowRight } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { TableSkeleton } from "@/components/ui/table-skeleton";
import { ErrorState } from "@/components/ui/error-state";
import { EmptyState } from "@/components/ui/empty-state";
import { ConfidenceBadge } from "./ranking-table";
import { roiPerDay } from "@/lib/graph";
import { useCycles } from "@/lib/queries";
import { formatMoney, formatPercent } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/input";
import { cycleCurrency, formatMinutes, isProfitable } from "./cycle-helpers";
import { MODE_LABEL, MODE_TONE } from "@/components/ui/labels";


export function LiveCycles({ limit = 12, compact = false }: { limit?: number; compact?: boolean }) {
  const [includeIncomplete, setIncludeIncomplete] = React.useState(true);
  const q = useCycles({ maxLen: 4 });
  const rows = React.useMemo(() => (q.data ?? []).filter((c) => includeIncomplete || c.confidence !== "incomplete"), [q.data, includeIncomplete]);
  const positive = rows.filter(isProfitable);
  // Os «quase lá» são o que vigiar: na visão geral (compact) ficam os 3 mais próximos, na tela cheia 5.
  const nearMiss = rows.filter((c) => !isProfitable(c)).slice(0, compact ? 3 : 5);
  const shown = [...positive.slice(0, limit), ...nearMiss];
  const dataMode = q.data?.[0]?.data_mode;

  return (
    <Card data-testid="live-cycles">
      <CardHeader className="flex-row items-start justify-between gap-2">
        <div>
          <CardTitle>Cruzamento ao vivo</CardTitle>
          <CardDescription>
            Ciclos no grafo de posições (moeda@conta) que começam e terminam na mesma conta com o saldo já estacionado. Cada aresta inclui taxa, custos e prazo; o ROI é calculado sobre o saldo usado.
          </CardDescription>
        </div>
        <div className="flex flex-col items-end gap-1">
          <Badge variant={positive.length ? "gain" : "outline"}>{positive.length} lucrativo{positive.length === 1 ? "" : "s"}</Badge>
          {dataMode && <Badge variant={MODE_TONE[dataMode]} data-testid="cycles-mode">{MODE_LABEL[dataMode]}</Badge>}
        </div>
      </CardHeader>
      <CardContent className="space-y-3 p-0 sm:p-2">
        {!compact && (
          <div className="flex items-center justify-between gap-2 px-2 text-xs">
            <Label htmlFor="inc-incomplete" className="text-foreground">Incluir ciclos com custo pendente (estimativa incompleta)</Label>
            <Switch id="inc-incomplete" checked={includeIncomplete} onCheckedChange={setIncludeIncomplete} />
          </div>
        )}
        {q.isLoading ? (
          <TableSkeleton rows={4} cols={6} />
        ) : q.isError ? (
          <ErrorState title="Os ciclos não puderam ser calculados" error={q.error} onRetry={() => void q.refetch()} />
        ) : shown.length === 0 ? (
          <EmptyState kind="no-data" compact title="Nenhum ciclo com os saldos atuais" description="Um ciclo só começa onde há saldo estacionado; cadastre contas com saldo ou aguarde as cotações se moverem." />
        ) : (
          <Table scrollLabel="Ciclos do cruzamento ao vivo (rola para o lado)">
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>Início</TableHead>
                <TableHead>Caminho</TableHead>
                <TableHead className="text-right">Saldo usado</TableHead>
                <TableHead className="text-right">Ganho</TableHead>
                <TableHead className="text-right">ROI</TableHead>
                {!compact && <TableHead className="text-right">ROI/dia</TableHead>}
                <TableHead className="text-right">Prazo</TableHead>
                <TableHead>Confiança</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {shown.map((c, i) => {
                const currency = cycleCurrency(c.start);
                const profit = isProfitable(c);
                const incomplete = c.confidence === "incomplete";
                return (
                  <TableRow key={`${c.start}-${c.path.join(">")}-${i}`} className={cn(!profit && "text-muted")} data-testid="cycle-row" data-profitable={profit}>
                    <TableCell className="tnum whitespace-nowrap font-medium">{c.start}</TableCell>
                    <TableCell>
                      <div className="flex flex-wrap items-center gap-1 text-xs">
                        {c.edges.map((e, j) => (
                          <React.Fragment key={j}>
                            <span className="tnum rounded-sm bg-surface-2 px-1 py-0.5" title={e.via}>{e.to}</span>
                            {j < c.edges.length - 1 && <ArrowRight className="size-3 text-muted" aria-hidden />}
                          </React.Fragment>
                        ))}
                      </div>
                      {!compact && <p className="mt-0.5 text-xs text-muted">{c.edges.map((e) => e.via).join(" → ")}</p>}
                    </TableCell>
                    <TableCell className="tnum text-right">{formatMoney(c.amount_in, currency)}</TableCell>
                    <TableCell className={cn("tnum text-right font-semibold", incomplete ? "text-muted" : profit ? "text-gain" : "text-loss")}>
                      {incomplete && <span aria-hidden>≈ </span>}
                      {formatMoney(c.gain, currency, { sign: !incomplete })}
                      {incomplete && <span className="sr-only"> (não confirmado)</span>}
                    </TableCell>
                    <TableCell className={cn("tnum text-right", incomplete ? "text-muted" : profit ? "text-gain" : "text-loss")}>{formatPercent(c.roi, { sign: !incomplete })}</TableCell>
                    {!compact && (
                      <TableCell className="tnum text-right text-muted" data-testid="roi-day-cell">
                        {incomplete && <span aria-hidden>≈ </span>}
                        {formatPercent(roiPerDay(c), { sign: !incomplete })}
                      </TableCell>
                    )}
                    <TableCell className="tnum text-right text-muted">{formatMinutes(c.minutes)}</TableCell>
                    <TableCell><ConfidenceBadge c={c.confidence} /></TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}
        {nearMiss.length > 0 && <p className="px-2 pb-2 text-xs text-muted">As linhas em cinza são os ciclos mais próximos de virar lucro; servem para vigiar quando uma cotação se mover.</p>}
      </CardContent>
    </Card>
  );
}
