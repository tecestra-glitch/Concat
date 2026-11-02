"use client";
import * as React from "react";
import { DEFAULT_FILTERS, Filters, type MarketFilters } from "@/components/markets/filters";
import { PriceCards } from "@/components/markets/price-cards";
import { QuoteTable } from "@/components/markets/quote-table";
import { RankingTable } from "@/components/opportunities/ranking-table";
import { PriceChart } from "@/components/charts/price-chart";
import { VolatilityCard } from "@/components/markets/volatility-card";
import { useHistory, useOpportunities, useQuotes, useSources } from "@/lib/queries";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { historyKey } from "@/lib/api/demo-data";
import { Badge } from "@/components/ui/badge";
import { formatAge } from "@/lib/format";
import { useSettings } from "@/lib/settings";
import type { Quote } from "@/lib/api/types";
import { PageHeader } from "@/components/shell/page-header";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@radix-ui/react-collapsible";
import { Button } from "@/components/ui/button";
import { SlidersHorizontal } from "lucide-react";
import { LiveCycles } from "@/components/opportunities/live-cycles";

export function Overview() {
  const { settings } = useSettings();
  const [filters, setFilters] = React.useState<MarketFilters>({ ...DEFAULT_FILTERS, capital: String(settings.defaultCapital) });
  const { data: sources = [] } = useSources();
  const quotesQ = useQuotes({ city: filters.city, base: filters.base, source: filters.source });
  const quotes = React.useMemo(() => (quotesQ.data ?? []).filter((q) => q.amount_base === null), [quotesQ.data]);
  const [selected, setSelected] = React.useState<Quote | null>(null);
  const chartQuote = selected ?? quotes.find((q) => q.base === "USD" && q.quote === "PYG") ?? quotes[0] ?? null;
  const key = chartQuote ? historyKey(chartQuote) : null;
  const hist = useHistory(key);
  const opps = useOpportunities(Number(filters.capital));
  const main = (opps.data ?? []).filter((o) => o.in_main_ranking);
  const [filtersOpen, setFiltersOpen] = React.useState(false);

  return (
    <div className="space-y-4">
      <PageHeader title="Visão geral" description="Preços BRL · USD · PYG, ranking de oportunidades e estado das fontes.">
        <Collapsible open={filtersOpen} onOpenChange={setFiltersOpen} className="sm:hidden">
          <CollapsibleTrigger asChild>
            <Button variant="secondary" size="sm" aria-expanded={filtersOpen}><SlidersHorizontal /> Filtros</Button>
          </CollapsibleTrigger>
          <CollapsibleContent className="mt-2"><Filters value={filters} onChange={setFilters} /></CollapsibleContent>
        </Collapsible>
        <div className="hidden sm:block"><Filters value={filters} onChange={setFilters} /></div>
      </PageHeader>

      {quotesQ.isLoading ? <Skeleton className="h-28" /> : <PriceCards quotes={quotes} />}

      <div className="grid gap-4 xl:grid-cols-[3fr_2fr]">
        <Card className="min-w-0">
          <CardHeader className="flex-row items-center justify-between">
            <div>
              <CardTitle>Cotações</CardTitle>
              <CardDescription>Compra/venda por fonte. Clique numa linha para ver o gráfico.</CardDescription>
            </div>
            <Badge variant="outline">{quotes.length} linhas</Badge>
          </CardHeader>
          <CardContent className="p-0 sm:p-2">
            {quotesQ.isError ? (
              <p role="alert" className="p-4 text-sm text-loss">Falha ao carregar cotações: {(quotesQ.error as Error).message}</p>
            ) : (
              <QuoteTable quotes={quotes} sources={sources} onSelect={setSelected} selectedId={chartQuote?.id} compact />
            )}
          </CardContent>
        </Card>
        <Card className="min-w-0">
          <CardHeader>
            <CardTitle>Ranking de oportunidades</CardTitle>
            <CardDescription>Ganho líquido e ROI para o orçamento filtrado. Presencial só entra se superar o digital em ≥ 1 p.p.</CardDescription>
          </CardHeader>
          <CardContent className="p-0 sm:p-2">
            {opps.isLoading ? <Skeleton className="m-3 h-32" /> : <RankingTable items={main} emptyText="Nenhuma oportunidade no ranking principal para este orçamento." />}
          </CardContent>
        </Card>
      </div>

      <LiveCycles limit={6} compact />

      <div className="grid gap-4 xl:grid-cols-[3fr_2fr]">
        <Card className="min-w-0">
          <CardHeader className="flex-row items-center justify-between">
            <div>
              <CardTitle>Gráfico intradiário</CardTitle>
              <CardDescription>{chartQuote ? `${sources.find((s) => s.id === chartQuote.source_id)?.name ?? chartQuote.source_id} · ${chartQuote.base}/${chartQuote.quote} · ${chartQuote.unit_note}` : "Selecione uma cotação"}</CardDescription>
            </div>
            {chartQuote && <Badge variant="outline">idade {formatAge(chartQuote.captured_at, Date.parse(hist.data?.points.at(-1)?.t ?? chartQuote.captured_at) + 1)}</Badge>}
          </CardHeader>
          <CardContent>{hist.isLoading || !hist.data ? <Skeleton className="h-[220px]" /> : <PriceChart points={hist.data.points} />}</CardContent>
        </Card>
        <div className="space-y-4">
          {hist.data && <VolatilityCard points={hist.data.points} />}
          <SourcesStatus />
        </div>
      </div>
    </div>
  );
}

function SourcesStatus() {
  const { data: sources = [] } = useSources();
  const tone: Record<string, "gain" | "warn" | "loss" | "outline"> = { ok: "gain", degraded: "warn", stale: "warn", blocked: "loss", unknown: "outline" };
  return (
    <Card data-testid="sources-status">
      <CardHeader>
        <CardTitle>Estado das fontes</CardTitle>
        <CardDescription>Idade da última coleta bem-sucedida por coletor.</CardDescription>
      </CardHeader>
      <CardContent className="grid grid-cols-1 gap-1.5 text-sm sm:grid-cols-2">
        {sources.map((s) => (
          <div key={s.id} className="flex items-center justify-between gap-2 rounded-md border border-border px-2 py-1.5">
            <span className="truncate">{s.name}</span>
            <span className="flex items-center gap-2 text-xs text-muted">
              <span className="tnum">{formatAge(s.last_success_at)}</span>
              <Badge variant={tone[s.health] ?? "outline"}>{s.health}</Badge>
            </span>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
