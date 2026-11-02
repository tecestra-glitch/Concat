"use client";
import * as React from "react";
import type { SimulationRequest } from "@/lib/api/types";
import { useSimulation } from "@/lib/queries";
import { useSettings } from "@/lib/settings";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Button } from "@/components/ui/button";
import { RankingTable } from "@/components/opportunities/ranking-table";
import { Skeleton } from "@/components/ui/skeleton";
import { formatMoney } from "@/lib/format";

export function Simulator() {
  const { settings } = useSettings();
  const [capital, setCapital] = React.useState(String(settings.defaultCapital));
  const [objective, setObjective] = React.useState<SimulationRequest["objective"]>("cycle");
  const [valuation, setValuation] = React.useState<SimulationRequest["valuation_currency"]>(settings.valuationCurrency);
  const [digital, setDigital] = React.useState(true);
  const [physical, setPhysical] = React.useState(true);
  const [req, setReq] = React.useState<SimulationRequest | null>(null);
  const q = useSimulation(req);
  const error = (() => {
    const n = Number(capital);
    if (!Number.isFinite(n) || n < 5000 || n > 50000) return "Informe um valor entre R$ 5.000 e R$ 50.000.";
    if (!digital && !physical) return "Selecione ao menos um canal.";
    return null;
  })();

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (error) return;
    const channels: SimulationRequest["channels"] = [];
    if (digital) channels.push("digital");
    if (physical) channels.push("physical");
    setReq({ capital_brl: capital, objective, valuation_currency: valuation, channels, amounts: ["5000", "10000", "25000", "50000"] });
  };

  return (
    <div className="grid gap-4 lg:grid-cols-[20rem_1fr]">
      <Card>
        <CardHeader>
          <CardTitle>Parâmetros</CardTitle>
          <CardDescription>Cada etapa é simulada sobre o valor recebido na etapa anterior. Custos desconhecidos ficam pendentes.</CardDescription>
        </CardHeader>
        <CardContent>
          <form className="grid gap-3" onSubmit={submit} noValidate>
            <div className="grid gap-1">
              <Label htmlFor="capital">Capital (BRL)</Label>
              <Input id="capital" inputMode="decimal" value={capital} onChange={(e) => setCapital(e.target.value)} aria-describedby="capital-help" aria-invalid={!!error && error.startsWith("Informe")} />
              <p id="capital-help" className="text-xs text-muted">Pesquisa adaptativa entre R$ 5 mil e R$ 50 mil, começando por 5 / 10 / 25 / 50 mil.</p>
              <div className="flex flex-wrap gap-1">
                {[5000, 10000, 25000, 50000].map((v) => (
                  <Button key={v} type="button" size="sm" variant={capital === String(v) ? "default" : "secondary"} onClick={() => setCapital(String(v))}>{formatMoney(v, "BRL")}</Button>
                ))}
              </div>
            </div>
            <div className="grid gap-1">
              <Label htmlFor="objective">Objetivo</Label>
              <Select value={objective} onValueChange={(v) => setObjective(v as SimulationRequest["objective"])}>
                <SelectTrigger id="objective"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="cycle">Ciclo fechado (lucro)</SelectItem>
                  <SelectItem value="remittance">Remessa (economia)</SelectItem>
                  <SelectItem value="purchase">Pagar uma compra (economia)</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-1">
              <Label htmlFor="valuation">Moeda de avaliação</Label>
              <Select value={valuation} onValueChange={(v) => setValuation(v as SimulationRequest["valuation_currency"])}>
                <SelectTrigger id="valuation"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="BRL">BRL (padrão)</SelectItem>
                  <SelectItem value="USD">USD</SelectItem>
                  <SelectItem value="PYG">PYG</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-center justify-between rounded-md border border-border p-2">
              <Label htmlFor="ch-digital" className="text-sm text-foreground">Canal digital</Label>
              <Switch id="ch-digital" checked={digital} onCheckedChange={setDigital} />
            </div>
            <div className="flex items-center justify-between rounded-md border border-border p-2">
              <Label htmlFor="ch-physical" className="text-sm text-foreground">Canal presencial</Label>
              <Switch id="ch-physical" checked={physical} onCheckedChange={setPhysical} />
            </div>
            {error && <p role="alert" className="text-xs text-loss">{error}</p>}
            <Button type="submit" disabled={!!error || q.isFetching}>{q.isFetching ? "Simulando…" : "Simular rotas"}</Button>
          </form>
        </CardContent>
      </Card>
      <div className="min-w-0 space-y-3">
        {!req && <p className="rounded-md border border-dashed border-border p-6 text-center text-sm text-muted">Defina os parâmetros e clique em Simular rotas.</p>}
        {q.isLoading && <Skeleton className="h-40" />}
        {q.isError && <p role="alert" className="text-sm text-loss">Falha ao simular: {(q.error as Error).message}</p>}
        {q.data && (
          <>
            <div className="flex flex-wrap gap-2 text-xs text-muted" data-testid="search-summary">
              <span>Valores testados: {q.data.search.amounts_tested.map((a) => formatMoney(a, "BRL")).join(", ")}</span>
              {q.data.search.boundaries.length > 0 && <span>· Fronteiras: {q.data.search.boundaries.join("; ")}</span>}
            </div>
            <RankingTable title="Ranking principal" items={q.data.opportunities.filter((o) => o.in_main_ranking)} emptyText="Nenhuma rota atingiu os critérios do ranking principal." />
            <RankingTable title="Ranking secundário (abaixo do limite ou sem ganho)" items={q.data.opportunities.filter((o) => !o.in_main_ranking)} emptyText="—" />
          </>
        )}
      </div>
    </div>
  );
}
