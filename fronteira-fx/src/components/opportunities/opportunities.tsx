"use client";
import * as React from "react";
import { RankingTable } from "./ranking-table";
import { useOpportunities } from "@/lib/queries";
import { PageHeader } from "@/components/shell/page-header";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { TableSkeleton } from "@/components/ui/table-skeleton";
import { ErrorState } from "@/components/ui/error-state";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Label } from "@/components/ui/input";
import { capitalOptions } from "@/lib/api/capitals";
import { formatMoney } from "@/lib/format";
import { useSettings } from "@/lib/settings";
import { LiveCycles } from "./live-cycles";

export function Opportunities() {
  const { settings, mode } = useSettings();
  const [capital, setCapital] = React.useState(String(settings.defaultCapital));
  const [channel, setChannel] = React.useState("all");
  const capitals = capitalOptions(mode, settings.defaultCapital);
  // O canal vai para a API (`channel=digital|physical`); "all" é removido pelo cliente.
  const q = useOpportunities({ capital, channel });
  const items = q.data ?? [];
  const main = items.filter((o) => o.in_main_ranking);
  const secondary = items.filter((o) => !o.in_main_ranking);
  const body = (list: typeof items) =>
    q.isLoading ? <TableSkeleton rows={5} cols={6} /> : q.isError ? <ErrorState title="As oportunidades não carregaram" error={q.error} onRetry={() => void q.refetch()} /> : <RankingTable items={list} />;
  return (
    <div className="space-y-4">
      <PageHeader title="Oportunidades" description="Digital primeiro: qualquer ganho líquido positivo aparece. Presencial só entra no principal se superar o melhor digital comparável em ≥ 1 ponto percentual.">
        <div className="flex gap-2">
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
      <Tabs defaultValue="principal">
        <TabsList><TabsTrigger value="principal">Ranking principal ({main.length})</TabsTrigger><TabsTrigger value="secundario">Secundário ({secondary.length})</TabsTrigger><TabsTrigger value="cruzamento">Cruzamento ao vivo</TabsTrigger></TabsList>
        <TabsContent value="principal"><Card><CardContent className="p-0 sm:p-2">{body(main)}</CardContent></Card></TabsContent>
        <TabsContent value="secundario">
          <Card>
            <CardHeader><CardTitle>Fora do ranking principal</CardTitle><CardDescription>Rotas sem ganho líquido ou presenciais abaixo do limite de +1 p.p. Abra uma linha para ver o motivo.</CardDescription></CardHeader>
            <CardContent className="p-0 sm:p-2">{body(secondary)}</CardContent>
          </Card>
        </TabsContent>
        <TabsContent value="cruzamento"><LiveCycles /></TabsContent>
      </Tabs>
    </div>
  );
}
