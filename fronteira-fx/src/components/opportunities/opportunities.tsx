"use client";
import * as React from "react";
import { RankingTable } from "./ranking-table";
import { useOpportunities } from "@/lib/queries";
import { PageHeader } from "@/components/shell/page-header";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { FxSegmented } from "@/components/ui/fx/fx-segmented";
import { TableSkeleton } from "@/components/ui/table-skeleton";
import { ErrorState } from "@/components/ui/error-state";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Label } from "@/components/ui/input";
import { capitalOptions } from "@/lib/api/capitals";
import { formatMoney } from "@/lib/format";
import { useSettings } from "@/lib/settings";
import { LiveCycles } from "./live-cycles";

type OppTab = "principal" | "secundario" | "cruzamento" | "presencial";

export function Opportunities() {
  const { settings, mode } = useSettings();
  const [capital, setCapital] = React.useState(String(settings.defaultCapital));
  const [channel, setChannel] = React.useState("all");
  const [tab, setTab] = React.useState<OppTab>("principal");
  const capitals = capitalOptions(mode, settings.defaultCapital);
  // Modo celular por padrão. Escolher o canal presencial (ou abrir a aba) traz o resto, com `mode=todos`.
  const presencial = channel === "physical";
  const routeMode = presencial ? "todos" : "celular";
  // O canal vai para a API (`channel=digital|physical`); "all" é removido pelo cliente.
  const q = useOpportunities({ capital, channel, mode: routeMode });
  const qPresencial = useOpportunities({ capital, channel: "physical", mode: "todos" });
  const items = q.data ?? [];
  const presencialItems = (qPresencial.data ?? []).filter((o) => o.channel === "physical");
  const main = items.filter((o) => o.in_main_ranking);
  const secondary = items.filter((o) => !o.in_main_ranking);
  const body = (list: typeof items) =>
    q.isLoading ? <TableSkeleton rows={5} cols={6} /> : q.isError ? <ErrorState title="As oportunidades não carregaram" error={q.error} onRetry={() => void q.refetch()} /> : <RankingTable items={list} />;
  const tabs = [
    { id: "principal" as const, label: `Ranking principal (${main.length})` },
    { id: "secundario" as const, label: `Secundário (${secondary.length})` },
    { id: "cruzamento" as const, label: "Cruzamento ao vivo" },
    { id: "presencial" as const, label: "Presencial (opcional)" },
  ];
  return (
    <div className="space-y-4">
      <PageHeader title="Oportunidades" description="Pelo celular: aqui entram só as rotas que dá para fazer inteiras no app, sem levar dinheiro em espécie de uma cidade para outra. O presencial fica na aba própria.">
        <div className="flex flex-wrap gap-2">
          <div className="grid gap-1">
            <Label htmlFor="opp-capital">Orçamento</Label>
            <Select value={capital} onValueChange={setCapital}>
              <SelectTrigger id="opp-capital" className="w-36" aria-label="Orçamento"><SelectValue /></SelectTrigger>
              <SelectContent>{capitals.map((c) => <SelectItem key={c} value={String(c)}>{formatMoney(c, "BRL")}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div className="grid gap-1">
            <Label htmlFor="opp-channel">Canal</Label>
            <Select value={channel} onValueChange={setChannel}>
              <SelectTrigger id="opp-channel" className="w-36" aria-label="Canal"><SelectValue /></SelectTrigger>
              <SelectContent><SelectItem value="all">Todos</SelectItem><SelectItem value="digital">Digital</SelectItem><SelectItem value="physical">Presencial</SelectItem></SelectContent>
            </Select>
          </div>
        </div>
      </PageHeader>
      <FxSegmented items={tabs} value={tab} onValueChange={setTab} idPrefix="opp-tab" aria-label="Seções de oportunidades" testId="opp-tabs" className="max-w-xl" />

      {tab === "principal" && (
        <section role="tabpanel" id="opp-panel-principal" aria-labelledby="opp-tab-principal">
          <Card><CardContent className="p-0 sm:p-2">{body(main)}</CardContent></Card>
        </section>
      )}
      {tab === "secundario" && (
        <section role="tabpanel" id="opp-panel-secundario" aria-labelledby="opp-tab-secundario">
          <Card>
            <CardHeader><CardTitle>Fora do ranking principal</CardTitle><CardDescription>Rotas sem ganho líquido ou presenciais abaixo do limite de +1 p.p. Abra uma linha para ver o motivo.</CardDescription></CardHeader>
            <CardContent className="p-0 sm:p-2">{body(secondary)}</CardContent>
          </Card>
        </section>
      )}
      {tab === "cruzamento" && (
        <section role="tabpanel" id="opp-panel-cruzamento" aria-labelledby="opp-tab-cruzamento">
          <LiveCycles />
        </section>
      )}
      {tab === "presencial" && (
        <section role="tabpanel" id="opp-panel-presencial" aria-labelledby="opp-tab-presencial">
          <Card>
            <CardHeader>
              <CardTitle>Presencial (opcional)</CardTitle>
              <CardDescription data-testid="presencial-aviso">Exige ir à casa de câmbio: estas rotas têm uma perna em espécie, então não entram no ranking pelo celular.</CardDescription>
            </CardHeader>
            <CardContent className="p-0 sm:p-2">
              {qPresencial.isLoading ? <TableSkeleton rows={5} cols={6} /> : <RankingTable items={presencialItems} />}
            </CardContent>
          </Card>
        </section>
      )}
    </div>
  );
}
