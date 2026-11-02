"use client";
/**
 * Cruzamento ao vivo: ciclos lucrativos detectados no grafo de posições a partir do capital
 * já estacionado em cada conta. Em modo demonstração usa as arestas ilustrativas da demo;
 * em modo real o backend expõe GET /v1/opportunities/cycles (mesma estrutura).
 */
import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ConfidenceBadge } from "./ranking-table";
import { findCycles, roiPerDay, type Cycle } from "@/lib/graph";
import { demoEdges, demoParkedBalances } from "@/lib/api/demo-graph";
import { useSettings } from "@/lib/settings";
import { formatMoney, formatPercent } from "@/lib/format";
import { API_URL } from "@/lib/api/client";
import type { Currency } from "@/lib/api/types";
import { cn } from "@/lib/utils";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/input";

interface CycleRow extends Cycle {
  currency: Currency;
}

async function loadCycles(mode: "demo" | "real", includeIncomplete: boolean): Promise<CycleRow[]> {
  let cycles: Cycle[];
  if (mode === "real" && API_URL) {
    const res = await fetch(`${API_URL}/v1/opportunities/cycles?max_len=4`);
    if (!res.ok) throw new Error(`${res.status} ao buscar ciclos`);
    cycles = (await res.json()) as Cycle[];
  } else {
    cycles = findCycles(demoEdges(), demoParkedBalances(), { maxLen: 4 });
  }
  return cycles
    .filter((c) => includeIncomplete || c.confidence !== "incomplete")
    .map((c) => ({ ...c, currency: c.start.split("@")[0] as Currency }));
}

export function LiveCycles({ limit = 12, compact = false }: { limit?: number; compact?: boolean }) {
  const { mode } = useSettings();
  const [includeIncomplete, setIncludeIncomplete] = React.useState(true);
  const q = useQuery({ queryKey: ["cycles", mode, includeIncomplete], queryFn: () => loadCycles(mode, includeIncomplete), refetchInterval: mode === "real" ? 30_000 : false });
  const rows = q.data ?? [];
  const positive = rows.filter((c) => c.gain > 0);
  const nearMiss = rows.filter((c) => c.gain <= 0).slice(0, 5);
  const shown = [...positive.slice(0, limit), ...(compact ? [] : nearMiss)];

  return (
    <Card data-testid="live-cycles">
      <CardHeader className="flex-row items-start justify-between gap-2">
        <div>
          <CardTitle>Cruzamento ao vivo</CardTitle>
          <CardDescription>
            Ciclos no grafo de posições (moeda@conta) que começam e terminam na mesma conta com o saldo já estacionado. Cada aresta inclui taxa, custos e prazo; o ROI é calculado sobre o saldo usado.
          </CardDescription>
        </div>
        <Badge variant={positive.length ? "gain" : "outline"}>{positive.length} lucrativo{positive.length === 1 ? "" : "s"}</Badge>
      </CardHeader>
      <CardContent className="space-y-3 p-0 sm:p-2">
        {!compact && (
          <div className="flex items-center justify-between px-2 text-xs">
            <Label htmlFor="inc-incomplete" className="text-foreground">Incluir ciclos com custo pendente (estimativa incompleta)</Label>
            <Switch id="inc-incomplete" checked={includeIncomplete} onCheckedChange={setIncludeIncomplete} />
          </div>
        )}
        {q.isError && <p role="alert" className="p-3 text-sm text-loss">Falha ao calcular ciclos: {(q.error as Error).message}</p>}
        <Table>
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
            {shown.length === 0 && (
              <TableRow><TableCell colSpan={8} className="py-6 text-center text-muted">{q.isLoading ? "Calculando…" : "Nenhum ciclo encontrado com os saldos atuais."}</TableCell></TableRow>
            )}
            {shown.map((c, i) => (
              <TableRow key={`${c.start}-${i}`} className={cn(c.gain <= 0 && "opacity-70")}>
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
                  {!compact && <p className="mt-0.5 text-[11px] text-muted">{c.edges.map((e) => e.via).join(" → ")}</p>}
                </TableCell>
                <TableCell className="tnum text-right">{formatMoney(c.amountIn, c.currency)}</TableCell>
                <TableCell className={cn("tnum text-right font-semibold", c.gain > 0 ? "text-gain" : "text-loss")}>{formatMoney(c.gain, c.currency, { sign: true })}</TableCell>
                <TableCell className={cn("tnum text-right", c.gain > 0 ? "text-gain" : "text-loss")}>{formatPercent(c.roi, { sign: true })}</TableCell>
                {!compact && <TableCell className="tnum text-right text-muted">{formatPercent(roiPerDay(c), { sign: true })}</TableCell>}
                <TableCell className="tnum text-right text-muted">{c.minutes >= 1440 ? `${(c.minutes / 1440).toFixed(1).replace(".", ",")} d` : `${c.minutes} min`}</TableCell>
                <TableCell><ConfidenceBadge c={c.confidence} /></TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        {!compact && nearMiss.length > 0 && <p className="px-2 pb-2 text-[11px] text-muted">As últimas linhas (esmaecidas) são os ciclos mais próximos de virar lucro; servem para vigiar quando uma cotação se mover.</p>}
      </CardContent>
    </Card>
  );
}
