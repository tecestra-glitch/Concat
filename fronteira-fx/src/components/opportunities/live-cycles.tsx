"use client";
/**
 * Cruzamento ao vivo: ciclos no grafo de posições (moeda@lugar) a partir do saldo já estacionado.
 * Todos os modos passam por `useCycles` → `api.cycles(mode)` (D1: valores em string decimal; demo roda o
 * espelho TS do motor, real e simulação chamam GET /v1/opportunities/cycles). Mostra o ganho líquido nas
 * três moedas (destaque na de partida), canal de cada perna, aviso de declaração e a ação de gerar plano.
 */
import * as React from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, TriangleAlert } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { TableSkeleton } from "@/components/ui/table-skeleton";
import { ErrorState } from "@/components/ui/error-state";
import { EmptyState } from "@/components/ui/empty-state";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Input, Label } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { ConfidenceBadge } from "./ranking-table";
import { roiPerDay } from "@/lib/graph";
import { useCreatePlan, useCycles } from "@/lib/queries";
import { formatMoney, formatPercent } from "@/lib/format";
import { cn } from "@/lib/utils";
import { MODE_LABEL, MODE_TONE } from "@/components/ui/labels";
import type { Currency, Cycle } from "@/lib/api/types";
import { CYCLE_CURRENCIES, cycleCurrency, cycleGain, filterCycles, formatMinutes, isProfitable, parseMinGain, pathLabel, type CycleFilter } from "./cycle-helpers";
import { CycleDetail } from "./cycle-detail";
import { LegChannel } from "./leg-channel";

const INITIAL_FILTER: CycleFilter = { currency: "all", minGain: "", minCurrency: "BRL", includeIncomplete: true };

export function LiveCycles({ limit = 12, compact = false }: { limit?: number; compact?: boolean }) {
  const [filter, setFilter] = React.useState<CycleFilter>(INITIAL_FILTER);
  const [open, setOpen] = React.useState<Cycle | null>(null);
  const router = useRouter();
  const plan = useCreatePlan();
  const q = useCycles({ maxLen: 4 });
  const minGainOk = parseMinGain(filter.minGain).ok;
  const rows = React.useMemo(() => filterCycles(q.data ?? [], compact ? { ...INITIAL_FILTER, includeIncomplete: false } : filter), [q.data, filter, compact]);
  const positive = rows.filter(isProfitable);
  // Os «quase lá» são o que vigiar: na visão geral (compact) ficam os 3 mais próximos, na tela cheia 5.
  const nearMiss = rows.filter((c) => !isProfitable(c)).slice(0, compact ? 3 : 5);
  const shown = [...positive.slice(0, limit), ...nearMiss];
  const dataMode = q.data?.[0]?.data_mode;
  const set = (patch: Partial<CycleFilter>) => setFilter((f) => ({ ...f, ...patch }));

  const makePlan = async (c: Cycle) => {
    const p = await plan.mutateAsync({ start: c.start, path: c.path });
    router.push(`/planos/${p.id}`);
  };

  return (
    <Card data-testid="live-cycles">
      <CardHeader className="flex-row items-start justify-between gap-2">
        <div>
          <CardTitle>Cruzamento ao vivo</CardTitle>
          <CardDescription>
            Ciclos que começam e terminam no mesmo lugar, com o saldo já estacionado. O ganho aparece nas três moedas; a moeda de partida vem em destaque. Um custo desconhecido aparece como estimativa, nunca como lucro confirmado.
          </CardDescription>
        </div>
        <div className="flex flex-col items-end gap-1">
          <Badge variant={positive.length ? "gain" : "outline"}>{positive.length} lucrativo{positive.length === 1 ? "" : "s"}</Badge>
          {dataMode && <Badge variant={MODE_TONE[dataMode]} data-testid="cycles-mode">{MODE_LABEL[dataMode]}</Badge>}
        </div>
      </CardHeader>
      <CardContent className="space-y-3 p-0 sm:p-2">
        {!compact && (
          <form className="grid gap-3 px-2 sm:grid-cols-[repeat(3,minmax(0,1fr))_auto] sm:items-end" aria-label="Filtros do cruzamento" onSubmit={(e) => e.preventDefault()}>
            <div className="grid gap-1">
              <Label htmlFor="cyc-currency">Moeda de partida</Label>
              <Select value={filter.currency} onValueChange={(v) => set({ currency: v as CycleFilter["currency"] })}>
                <SelectTrigger id="cyc-currency" aria-label="Moeda de partida"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Todas</SelectItem>
                  {CYCLE_CURRENCIES.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="grid grid-cols-[minmax(0,1fr)_6rem] gap-2">
              <div className="grid gap-1">
                <Label htmlFor="cyc-min">Ganho mínimo</Label>
                <Input id="cyc-min" inputMode="decimal" placeholder="ex.: 20" value={filter.minGain} onChange={(e) => set({ minGain: e.target.value })} autoComplete="off" aria-invalid={!minGainOk} aria-describedby={minGainOk ? undefined : "cyc-min-err"} />
                {!minGainOk && <p id="cyc-min-err" role="alert" className="text-xs text-loss">Não entendi esse valor. Use, por exemplo, 20 ou 1.250,50.</p>}
              </div>
              <div className="grid gap-1">
                <Label htmlFor="cyc-min-cur">em</Label>
                <Select value={filter.minCurrency} onValueChange={(v) => set({ minCurrency: v as Currency })}>
                  <SelectTrigger id="cyc-min-cur" aria-label="Moeda do ganho mínimo"><SelectValue /></SelectTrigger>
                  <SelectContent>{CYCLE_CURRENCIES.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
                </Select>
              </div>
            </div>
            <div className="flex items-center justify-between gap-2 text-xs sm:justify-start">
              <Label htmlFor="inc-incomplete" className="text-foreground">Incluir ciclos com custo pendente (estimativa incompleta)</Label>
              <Switch id="inc-incomplete" checked={filter.includeIncomplete} onCheckedChange={(v) => set({ includeIncomplete: v })} />
            </div>
          </form>
        )}
        {plan.isError && <p role="alert" className="px-2 text-xs text-loss">Não foi possível gerar o plano: {plan.error instanceof Error ? plan.error.message : "erro"}</p>}
        {q.isLoading ? (
          <TableSkeleton rows={4} cols={6} />
        ) : q.isError ? (
          <ErrorState title="Os ciclos não puderam ser calculados" error={q.error} onRetry={() => void q.refetch()} />
        ) : shown.length === 0 ? (
          <EmptyState kind={q.data?.length ? "no-match" : "no-data"} compact title={q.data?.length ? "Nenhum ciclo com esses filtros" : "Nenhum ciclo com os saldos atuais"} description={q.data?.length ? "Afrouxe o ganho mínimo ou troque a moeda de partida." : "Um ciclo só começa onde há saldo estacionado; cadastre contas com saldo ou aguarde as cotações se moverem."} />
        ) : (
          <Table scrollLabel="Ciclos do cruzamento ao vivo (rola para o lado)">
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>Início</TableHead>
                <TableHead>Caminho e canais</TableHead>
                <TableHead className="text-right">Saldo usado</TableHead>
                <TableHead className="text-right">Ganho líquido</TableHead>
                <TableHead className="text-right">ROI</TableHead>
                {!compact && <TableHead className="text-right">ROI/dia</TableHead>}
                <TableHead className="text-right">Prazo</TableHead>
                <TableHead>Confiança</TableHead>
                <TableHead><span className="sr-only">Ações</span></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {shown.map((c, i) => {
                const currency = cycleCurrency(c.start);
                const profit = isProfitable(c);
                const incomplete = c.confidence === "incomplete";
                const declaration = c.requires_declaration;
                return (
                  <TableRow key={`${c.start}-${c.path.join(">")}-${i}`} className={cn(!profit && "text-muted")} data-testid="cycle-row" data-profitable={profit}>
                    <TableCell className="tnum whitespace-nowrap font-medium">{c.start}</TableCell>
                    <TableCell>
                      <div className="flex flex-wrap items-center gap-1 text-xs">
                        {c.legs.map((leg, j) => (
                          <React.Fragment key={j}>
                            <span className="tnum rounded-sm bg-surface-2 px-1 py-0.5" title={leg.via}>{leg.to.replace("@", " · ")}</span>
                            {!compact && <LegChannel channel={leg.channel} className="py-0" />}
                            {j < c.legs.length - 1 && <ArrowRight className="size-3 text-muted" aria-hidden />}
                          </React.Fragment>
                        ))}
                      </div>
                      {!compact && <p className="mt-0.5 break-words text-xs text-muted">{c.legs.map((l) => l.via).join(" → ")}</p>}
                      {declaration && <Badge variant="warn" className="mt-1"><TriangleAlert className="size-3" aria-hidden />Declarar acima de US$ 10 mil</Badge>}
                    </TableCell>
                    <TableCell className="tnum text-right">{formatMoney(c.amount_in, currency)}</TableCell>
                    <TableCell className={cn("tnum text-right", incomplete ? "text-muted" : profit ? "text-gain" : "text-loss")} data-testid="gain-cell">
                      <GainCell c={c} incomplete={incomplete} compact={compact} />
                    </TableCell>
                    <TableCell className={cn("tnum text-right", incomplete ? "text-muted" : profit ? "text-gain" : "text-loss")}>
                      {incomplete && <span aria-hidden>≈ </span>}
                      {formatPercent(c.roi, { sign: !incomplete })}
                    </TableCell>
                    {!compact && (
                      <TableCell className="tnum text-right text-muted" data-testid="roi-day-cell">
                        {incomplete && <span aria-hidden>≈ </span>}
                        {formatPercent(roiPerDay(c), { sign: !incomplete })}
                      </TableCell>
                    )}
                    <TableCell className="tnum text-right text-muted">{formatMinutes(c.minutes)}</TableCell>
                    <TableCell><ConfidenceBadge c={c.confidence} /></TableCell>
                    <TableCell>
                      <div className="flex flex-col items-end gap-1 whitespace-nowrap">
                        <Button variant="ghost" size="sm" onClick={() => setOpen(c)} aria-label={`Ver detalhes do ciclo ${c.start} → ${pathLabel(c.path)}`}>Detalhes</Button>
                        <Button size="sm" variant={profit ? "default" : "outline"} disabled={!profit || plan.isPending} onClick={() => void makePlan(c)} title={profit ? undefined : "Só ciclos com ganho líquido positivo viram plano"} aria-label={`Gerar plano do ciclo ${c.start}`}>
                          Gerar plano
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}
        {nearMiss.length > 0 && <p className="px-2 pb-2 text-xs text-muted">As linhas em cinza são os ciclos mais próximos de virar lucro; servem para vigiar quando uma cotação se mover.</p>}
      </CardContent>
      <CycleDetail cycle={open} onClose={() => setOpen(null)} />
    </Card>
  );
}

/** Ganho na moeda de partida em destaque; as outras duas moedas abaixo. `null` vira «não convertido». */
function GainCell({ c, incomplete, compact }: { c: Cycle; incomplete: boolean; compact: boolean }) {
  const start = cycleCurrency(c.start);
  const headline = formatMoney(c.gain, start, { sign: !incomplete });
  return (
    <div>
      <span className="font-semibold">
        {incomplete && <span aria-hidden>≈ </span>}
        {headline}
      </span>
      {incomplete && <span className="sr-only"> (não confirmado)</span>}
      {!compact && (
        <ul className="mt-0.5 space-y-0 text-xs font-normal text-muted" aria-label="Ganho nas três moedas">
          {CYCLE_CURRENCIES.filter((cur) => cur !== start).map((cur) => {
            const v = cycleGain(c, cur);
            return <li key={cur} data-currency={cur}>{v === null ? `${cur} —` : `${cur} ${incomplete ? "≈ " : ""}${formatMoney(v, cur, { sign: !incomplete })}`}</li>;
          })}
        </ul>
      )}
      {incomplete && <span className="block text-xs font-normal">não confirmado</span>}
    </div>
  );
}
