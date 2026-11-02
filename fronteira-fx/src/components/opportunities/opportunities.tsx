"use client";
import * as React from "react";
import { RankingTable } from "./ranking-table";
import { useOpportunities } from "@/lib/queries";
import { PageHeader } from "@/components/shell/page-header";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Label } from "@/components/ui/input";
import { DEMO_CAPITALS } from "@/lib/api/demo-data";
import { useSettings } from "@/lib/settings";
import { LiveCycles } from "./live-cycles";

export function Opportunities() {
  const { settings } = useSettings();
  const [capital, setCapital] = React.useState(String(settings.defaultCapital));
  const [channel, setChannel] = React.useState("all");
  const q = useOpportunities(Number(capital));
  const items = (q.data ?? []).filter((o) => channel === "all" || o.channel === channel);
  const main = items.filter((o) => o.in_main_ranking);
  const secondary = items.filter((o) => !o.in_main_ranking);
  return (
    <div className="space-y-4">
      <PageHeader title="Oportunidades" description="Digital primeiro: qualquer ganho líquido positivo aparece. Presencial só entra no principal se superar o melhor digital comparável em ≥ 1 ponto percentual.">
        <div className="flex gap-2">
          <div className="grid gap-1"><Label>Orçamento</Label>
            <Select value={capital} onValueChange={setCapital}><SelectTrigger className="w-36" aria-label="Orçamento"><SelectValue /></SelectTrigger><SelectContent>{DEMO_CAPITALS.map((c) => <SelectItem key={c} value={String(c)}>R$ {c.toLocaleString("pt-BR")}</SelectItem>)}</SelectContent></Select>
          </div>
          <div className="grid gap-1"><Label>Canal</Label>
            <Select value={channel} onValueChange={setChannel}><SelectTrigger className="w-36" aria-label="Canal"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">Todos</SelectItem><SelectItem value="digital">Digital</SelectItem><SelectItem value="physical">Presencial</SelectItem></SelectContent></Select>
          </div>
        </div>
      </PageHeader>
      <Tabs defaultValue="principal">
        <TabsList><TabsTrigger value="principal">Ranking principal ({main.length})</TabsTrigger><TabsTrigger value="secundario">Secundário ({secondary.length})</TabsTrigger><TabsTrigger value="cruzamento">Cruzamento ao vivo</TabsTrigger></TabsList>
        <TabsContent value="principal"><Card><CardContent className="p-0 sm:p-2">{q.isLoading ? <Skeleton className="m-3 h-40" /> : <RankingTable items={main} />}</CardContent></Card></TabsContent>
        <TabsContent value="secundario">
          <Card>
            <CardHeader><CardTitle>Fora do ranking principal</CardTitle><CardDescription>Rotas sem ganho líquido ou presenciais abaixo do limite de +1 p.p. Clique para ver o motivo.</CardDescription></CardHeader>
            <CardContent className="p-0 sm:p-2">{q.isLoading ? <Skeleton className="m-3 h-40" /> : <RankingTable items={secondary} />}</CardContent>
          </Card>
        </TabsContent>
        <TabsContent value="cruzamento"><LiveCycles /></TabsContent>
      </Tabs>
    </div>
  );
}
