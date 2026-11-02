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
import { TableSkeleton } from "@/components/ui/table-skeleton";
import { ErrorState } from "@/components/ui/error-state";
import { EmptyState } from "@/components/ui/empty-state";
import { Badge } from "@/components/ui/badge";
import { HEALTH_LABEL, HEALTH_TONE } from "@/components/ui/labels";
import { Delta } from "@/components/ui/delta";
import { formatAge, toNumber } from "@/lib/format";
import { useNow } from "@/lib/use-now";
import { useSettings } from "@/lib/settings";
import type { Quote, Source } from "@/lib/api/types";
import { PageHeader } from "@/components/shell/page-header";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@radix-ui/react-collapsible";
import { Button } from "@/components/ui/button";
import { SlidersHorizontal } from "lucide-react";
import { LiveCycles } from "@/components/opportunities/live-cycles";

const NO_SOURCES: Source[] = [];

export function Overview() {
  const { settings, mode } = useSettings();
  const [filters, setFilters] = React.useState<MarketFilters>({ ...DEFAULT_FILTERS, capital: String(settings.defaultCapital) });
  const sourcesQ = useSources();
  const sources = sourcesQ.data ?? NO_SOURCES;
  const quotesQ = useQuotes({ city: filters.city, base: filters.base, source: filters.source });
  const quotes = React.useMemo(() => (quotesQ.data ?? []).filter((q) => q.amount_base === null), [quotesQ.data]);
  const [selected, setSelected] = React.useState<Quote | null>(null);
  const chartQuote = selected ?? quotes.find((q) => q.base === "USD" && q.quote === "PYG" && q.kind !== "market_reference") ?? quotes[0] ?? null;
  const hist = useHistory(chartQuote ? chartQuote.series_key : null);
  const opps = useOpportunities({ capital: filters.capital });
  const main = (opps.data ?? []).filter((o) => o.in_main_ranking);
  const [filtersOpen, setFiltersOpen] = React.useState(false);
  const now = useNow();
  const srcName = React.useCallback((id: string) => sources.find((s) => s.id === id)?.name ?? id, [sources]);
  const reference = React.useMemo(() => {
    if (!chartQuote) return null;
    const r = quotes.find((x) => x.kind === "market_reference" && x.base === chartQuote.base && x.quote === chartQuote.quote);
    return r && r.buy !== null ? { value: r.buy, title: srcName(r.source_id) } : null;
  }, [quotes, chartQuote, srcName]);
  const periodChange = React.useMemo(() => {
    const mids = (hist.data?.points ?? []).map((p) => toNumber(p.mid)).filter((v): v is number => v !== null && v > 0);
    return mids.length >= 2 ? (mids[mids.length - 1] - mids[0]) / mids[0] : null;
  }, [hist.data]);

  return (
    <div className="space-y-4">
      <PageHeader title="Visão geral" description="Preços BRL · USD · PYG, ranking de oportunidades e estado das fontes.">
        <Collapsible open={filtersOpen} onOpenChange={setFiltersOpen} className="sm:hidden">
          <CollapsibleTrigger asChild>
            <Button variant="secondary" size="sm" aria-expanded={filtersOpen}><SlidersHorizontal /> Filtros</Button>
          </CollapsibleTrigger>
          <CollapsibleContent className="mt-2"><Filters value={filters} onChange={setFilters} idPrefix="fm" /></CollapsibleContent>
        </Collapsible>
        <div className="hidden sm:block"><Filters value={filters} onChange={setFilters} /></div>
      </PageHeader>

      {quotesQ.isLoading ? <Skeleton className="h-28" /> : quotesQ.isError ? <ErrorState compact title="As cotações não carregaram" error={quotesQ.error} onRetry={() => void quotesQ.refetch()} /> : <PriceCards quotes={quotes} sources={sources} />}

      <div className="grid gap-4 xl:grid-cols-[3fr_2fr]">
        <Card className="min-w-0">
          <CardHeader className="flex-row items-center justify-between">
            <div>
              <CardTitle>Cotações</CardTitle>
              <CardDescription>Compra e venda por fonte. Selecione uma linha para ver o gráfico.</CardDescription>
            </div>
            <Badge variant="outline">{quotes.length} linhas</Badge>
          </CardHeader>
          <CardContent className="p-0 sm:p-2">
            {quotesQ.isLoading ? (
              <TableSkeleton rows={6} cols={5} />
            ) : quotesQ.isError ? (
              <ErrorState title="As cotações não carregaram" error={quotesQ.error} onRetry={() => void quotesQ.refetch()} />
            ) : (
              <QuoteTable quotes={quotes} sources={sources} onSelect={setSelected} selectedId={chartQuote?.id} compact emptyKind={(quotesQ.data?.length ?? 0) === 0 ? "no-data" : "no-match"} />
            )}
          </CardContent>
        </Card>
        <Card className="min-w-0">
          <CardHeader>
            <CardTitle>Ranking de oportunidades</CardTitle>
            <CardDescription>Ganho líquido e ROI para o orçamento filtrado. Presencial só entra se superar o digital em ≥ 1 p.p.</CardDescription>
          </CardHeader>
          <CardContent className="p-0 sm:p-2">
            {opps.isLoading ? (
              <TableSkeleton rows={4} cols={5} />
            ) : opps.isError ? (
              <ErrorState title="O ranking não carregou" error={opps.error} onRetry={() => void opps.refetch()} />
            ) : (
              <RankingTable items={main} compact emptyText="Nenhuma oportunidade no ranking principal para este orçamento." />
            )}
          </CardContent>
        </Card>
      </div>

      <LiveCycles limit={6} compact />

      <div className="grid gap-4 xl:grid-cols-[3fr_2fr]">
        <Card className="min-w-0">
          <CardHeader className="flex-row items-center justify-between gap-2">
            <div>
              <CardTitle>Gráfico intradiário</CardTitle>
              <CardDescription>{chartQuote ? `${srcName(chartQuote.source_id)} · ${chartQuote.base}/${chartQuote.quote} · ${chartQuote.unit_note}` : "Selecione uma cotação"}</CardDescription>
            </div>
            {chartQuote && (
              <div className="flex flex-wrap items-center justify-end gap-1">
                {periodChange !== null && <Delta value={periodChange} className="text-xs" />}
                <Badge variant="outline" data-volatile>{now === 0 ? "…" : `${srcName(chartQuote.source_id)} · ${formatAge(chartQuote.captured_at, now)}`}</Badge>
              </div>
            )}
          </CardHeader>
          <CardContent>
            {!chartQuote && !quotesQ.isLoading ? (
              <EmptyState kind="no-data" compact title="Sem cotação para traçar" />
            ) : hist.isLoading || !chartQuote ? (
              <Skeleton className="h-[220px]" />
            ) : hist.isError ? (
              <ErrorState title="O histórico não carregou" error={hist.error} onRetry={() => void hist.refetch()} />
            ) : (hist.data?.points.length ?? 0) === 0 ? (
              <EmptyState kind="no-data" compact title="Sem histórico para esta série" description="A série ainda não tem pontos nas últimas 24 h." />
            ) : (
              <PriceChart points={hist.data!.points} quote={chartQuote.quote} pair={`${chartQuote.base}/${chartQuote.quote}`} reference={reference} watermark={mode === "demo" ? "DEMONSTRAÇÃO" : null} />
            )}
          </CardContent>
        </Card>
        <div className="space-y-4">
          {hist.data && hist.data.points.length > 0 && <VolatilityCard points={hist.data.points} />}
          <SourcesStatus />
        </div>
      </div>
    </div>
  );
}

function SourcesStatus() {
  const q = useSources();
  const now = useNow();
  const sources = q.data ?? [];
  return (
    <Card data-testid="sources-status">
      <CardHeader>
        <CardTitle>Estado das fontes</CardTitle>
        <CardDescription>Idade da última coleta bem-sucedida por coletor.</CardDescription>
      </CardHeader>
      <CardContent className="grid grid-cols-1 gap-1.5 text-sm sm:grid-cols-2">
        {q.isLoading && <TableSkeleton rows={3} cols={2} className="col-span-full p-0" />}
        {q.isError && <ErrorState compact className="col-span-full" title="As fontes não carregaram" error={q.error} onRetry={() => void q.refetch()} />}
        {q.data && sources.length === 0 && <EmptyState compact className="col-span-full" kind="no-data" title="Nenhuma fonte cadastrada" />}
        {sources.map((s) => (
          <div key={s.id} className="flex items-center justify-between gap-2 rounded-md border border-border px-2 py-1.5">
            <span className="truncate">{s.name}</span>
            <span className="flex items-center gap-2 text-xs text-muted">
              <span className="tnum" data-volatile>{now === 0 ? "…" : formatAge(s.last_success_at, now)}</span>
              <Badge variant={HEALTH_TONE[s.health] ?? "outline"}>{HEALTH_LABEL[s.health] ?? s.health}</Badge>
            </span>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
