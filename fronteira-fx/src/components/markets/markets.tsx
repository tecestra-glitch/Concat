"use client";
import * as React from "react";
import { DEFAULT_FILTERS, Filters, type MarketFilters } from "./filters";
import { QuoteTable } from "./quote-table";
import { PriceChart } from "@/components/charts/price-chart";
import { VolatilityCard } from "./volatility-card";
import { useHistory, useQuotes, useSources } from "@/lib/queries";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { PageHeader } from "@/components/shell/page-header";
import { historyKey } from "@/lib/api/demo-data";
import type { Quote } from "@/lib/api/types";
import { CITY_LABEL } from "@/lib/api/types";
import { Skeleton } from "@/components/ui/skeleton";
import { formatMoney } from "@/lib/format";

export function Markets() {
  const [filters, setFilters] = React.useState<MarketFilters>(DEFAULT_FILTERS);
  const { data: sources = [] } = useSources();
  const q = useQuotes({ city: filters.city, base: filters.base, source: filters.source });
  const all = q.data ?? [];
  const tableQuotes = all.filter((x) => x.amount_base === null);
  const simulatorQuotes = all.filter((x) => x.amount_base !== null);
  const [selected, setSelected] = React.useState<Quote | null>(null);
  const chartQuote = selected ?? tableQuotes[0] ?? null;
  const hist = useHistory(chartQuote ? historyKey(chartQuote) : null);

  const byCity = ["CDE", "ASU", "PJC"] as const;

  return (
    <div className="space-y-4">
      <PageHeader title="Mercados" description="Cotações e spreads por cidade e instituição. Referência de mercado, indicativa e executável são distinguidas.">
        <Filters value={filters} onChange={setFilters} showCapital={false} />
      </PageHeader>
      <Tabs defaultValue="todas">
        <TabsList aria-label="Agrupamento">
          <TabsTrigger value="todas">Todas</TabsTrigger>
          <TabsTrigger value="cidade">Por cidade</TabsTrigger>
          <TabsTrigger value="simuladores">Simuladores por montante</TabsTrigger>
        </TabsList>
        <TabsContent value="todas">
          <Card><CardContent className="p-0 sm:p-2">{q.isLoading ? <Skeleton className="m-3 h-40" /> : <QuoteTable quotes={tableQuotes} sources={sources} onSelect={setSelected} selectedId={chartQuote?.id} />}</CardContent></Card>
        </TabsContent>
        <TabsContent value="cidade" className="space-y-4">
          {byCity.map((c) => (
            <Card key={c}>
              <CardHeader><CardTitle>{CITY_LABEL[c]}</CardTitle></CardHeader>
              <CardContent className="p-0 sm:p-2"><QuoteTable quotes={tableQuotes.filter((x) => x.city === c)} sources={sources} onSelect={setSelected} selectedId={chartQuote?.id} compact /></CardContent>
            </Card>
          ))}
          <Card>
            <CardHeader><CardTitle>Digital (sem cidade)</CardTitle><CardDescription>Operações digitais recebem identificação própria; nenhuma cidade é inventada.</CardDescription></CardHeader>
            <CardContent className="p-0 sm:p-2"><QuoteTable quotes={tableQuotes.filter((x) => x.city === null)} sources={sources} onSelect={setSelected} selectedId={chartQuote?.id} compact /></CardContent>
          </Card>
        </TabsContent>
        <TabsContent value="simuladores">
          <Card>
            <CardHeader><CardTitle>Cotações dependentes do valor</CardTitle><CardDescription>Cada linha preserva o contexto completo (origem, destino, pagamento, recebimento, banco, canal, promoção). Contextos diferentes nunca são misturados.</CardDescription></CardHeader>
            <CardContent className="p-0 sm:p-2">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead><tr className="border-b border-border text-left text-[11px] uppercase tracking-wide text-muted"><th className="px-2 py-2">Fonte</th><th className="px-2 py-2">Montante</th><th className="px-2 py-2">Recebimento</th><th className="px-2 py-2">Pagamento</th><th className="px-2 py-2 text-right">Taxa efetiva</th><th className="px-2 py-2">Prazo</th><th className="px-2 py-2">Promoção</th></tr></thead>
                  <tbody>
                    {simulatorQuotes.map((s) => (
                      <tr key={s.id} className="border-b border-border">
                        <td className="px-2 py-1.5 font-medium">{sources.find((x) => x.id === s.source_id)?.name ?? s.source_id}</td>
                        <td className="tnum px-2 py-1.5">{formatMoney(s.amount_base, s.base)}</td>
                        <td className="px-2 py-1.5">{s.context?.receive === "cash_pickup" ? "Retirada em loja" : s.context?.receive === "bank_account" ? "Conta bancária" : s.context?.receive ?? "—"}</td>
                        <td className="px-2 py-1.5">{s.context?.payment ?? "—"}</td>
                        <td className="tnum px-2 py-1.5 text-right">{Number(s.sell).toLocaleString("pt-BR", { maximumFractionDigits: 4 })} <span className="text-muted">{s.quote}/{s.base}</span></td>
                        <td className="px-2 py-1.5">{s.context?.duration ?? "—"}</td>
                        <td className="px-2 py-1.5 text-xs text-muted">{s.fees.map((f) => f.label).join(", ") || "—"}</td>
                      </tr>
                    ))}
                    {simulatorQuotes.length === 0 && <tr><td colSpan={7} className="px-2 py-6 text-center text-muted">Sem simulações para os filtros.</td></tr>}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
      <div className="grid gap-4 xl:grid-cols-[3fr_2fr]">
        <Card className="min-w-0">
          <CardHeader><CardTitle>Gráfico intradiário</CardTitle><CardDescription>{chartQuote ? `${chartQuote.source_id} · ${chartQuote.base}/${chartQuote.quote}` : "—"}</CardDescription></CardHeader>
          <CardContent>{hist.data ? <PriceChart points={hist.data.points} series={["buy", "sell", "mid"]} height={260} /> : <Skeleton className="h-[260px]" />}</CardContent>
        </Card>
        {hist.data && <VolatilityCard points={hist.data.points} />}
      </div>
    </div>
  );
}
