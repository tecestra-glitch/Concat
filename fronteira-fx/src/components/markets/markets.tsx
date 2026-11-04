"use client";
import * as React from "react";
import { DEFAULT_FILTERS, Filters, type MarketFilters } from "./filters";
import { QuoteTable } from "./quote-table";
import { PriceChart, SERIES_ALL } from "@/components/charts/price-chart";
import { VolatilityCard } from "./volatility-card";
import { PriceCards } from "./price-cards";
import { useHistory, useQuotes, useSources } from "@/lib/queries";
import { useSettings } from "@/lib/settings";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { PageHeader } from "@/components/shell/page-header";
import type { Quote, Source } from "@/lib/api/types";
import { CITY_LABEL } from "@/lib/api/types";
import { Skeleton } from "@/components/ui/skeleton";
import { TableSkeleton } from "@/components/ui/table-skeleton";
import { ErrorState } from "@/components/ui/error-state";
import { EmptyState } from "@/components/ui/empty-state";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { formatFee, formatMoney } from "@/lib/format";
import { formatRateFixed } from "@/components/ui/rate";

const CITIES = ["CDE", "ASU", "PJC"] as const;
const NO_QUOTES: Quote[] = [];
const NO_SOURCES: Source[] = [];
const PAYMENT_LABEL: Record<string, string> = { pix: "Pix", card: "Cartão", card_debit: "Cartão de débito", card_credit: "Cartão de crédito", bank_transfer: "Transferência", boleto: "Boleto", cash: "Dinheiro" };
const RECEIVE_LABEL: Record<string, string> = { cash_pickup: "Retirada em loja", bank_account: "Conta bancária", wallet: "Carteira digital" };
const PROMO_LABEL: Record<string, string> = { fee_100_off: "Tarifa 100 % off", fee_50_off: "Tarifa 50 % off", first_transfer_free: "Primeira remessa sem tarifa" };

function captionFor(f: MarketFilters, sourceName: string | undefined): string {
  const parts = [f.city === "all" ? "todas as cidades" : f.city === "digital" ? "digital" : CITY_LABEL[f.city as keyof typeof CITY_LABEL], f.base === "all" ? "USD e BRL" : `${f.base} cotado`, f.source === "all" ? "todas as fontes" : (sourceName ?? f.source), "por unidade"];
  return parts.join(" · ");
}

export function Markets() {
  const { mode } = useSettings();
  const [filters, setFilters] = React.useState<MarketFilters>(DEFAULT_FILTERS);
  const sourcesQ = useSources();
  const sources = sourcesQ.data ?? NO_SOURCES;
  const q = useQuotes({ city: filters.city, base: filters.base, source: filters.source });
  const byAmount = useQuotes({ city: filters.city, base: filters.base, source: filters.source, amount: filters.amount === "all" ? undefined : filters.amount });
  const all = q.data ?? NO_QUOTES;
  const tableQuotes = React.useMemo(() => all.filter((x) => x.amount_base === null), [all]);
  const simulatorQuotes = React.useMemo(() => (byAmount.data ?? []).filter((x) => x.amount_base !== null), [byAmount.data]);
  const [selected, setSelected] = React.useState<Quote | null>(null);
  const chartQuote = selected ?? tableQuotes.find((x) => x.kind !== "market_reference") ?? tableQuotes[0] ?? null;
  const hist = useHistory(chartQuote ? chartQuote.series_key : null);
  const reference = React.useMemo(() => {
    if (!chartQuote) return null;
    const r = all.find((x) => x.kind === "market_reference" && x.base === chartQuote.base && x.quote === chartQuote.quote);
    return r && r.buy !== null ? { value: r.buy, title: sources.find((s) => s.id === r.source_id)?.name ?? r.source_id } : null;
  }, [all, chartQuote, sources]);
  const srcName = (id: string) => sources.find((s) => s.id === id)?.name ?? id;
  const caption = captionFor(filters, sources.find((s) => s.id === filters.source)?.name);

  const tableState = (quotes: Quote[], compact = false) =>
    q.isLoading ? <TableSkeleton rows={6} cols={compact ? 5 : 8} /> : q.isError ? <ErrorState title="As cotações não carregaram" error={q.error} onRetry={() => void q.refetch()} /> : (
      <QuoteTable quotes={quotes} sources={sources} onSelect={setSelected} selectedId={chartQuote?.id} compact={compact} caption={compact ? undefined : caption} emptyKind={all.length === 0 ? "no-data" : "no-match"} />
    );

  return (
    <div className="space-y-4">
      <PageHeader title="Mercados" description="Cotações e spreads por cidade e instituição. Referência de mercado (≈, não executável), indicativa e executável são distinguidas.">
        <Filters value={filters} onChange={setFilters} showCapital={false} />
      </PageHeader>
      {/* Faixa de cotações no topo (ME1): melhor compra e venda por par, com bandeiras. */}
      {q.isLoading ? <Skeleton className="h-24" /> : q.isError ? null : <PriceCards quotes={tableQuotes} sources={sources} />}
      <Tabs defaultValue="todas">
        <TabsList aria-label="Agrupamento">
          <TabsTrigger value="todas">Todas</TabsTrigger>
          <TabsTrigger value="cidade">Por cidade</TabsTrigger>
          <TabsTrigger value="simuladores">Simuladores por montante</TabsTrigger>
        </TabsList>
        <TabsContent value="todas">
          <Card><CardContent className="p-0 sm:p-2">{tableState(tableQuotes)}</CardContent></Card>
        </TabsContent>
        <TabsContent value="cidade" className="space-y-4">
          {CITIES.map((c) => (
            <Card key={c}>
              <CardHeader><CardTitle>{CITY_LABEL[c]}</CardTitle></CardHeader>
              <CardContent className="p-0 sm:p-2">{tableState(tableQuotes.filter((x) => x.city === c), true)}</CardContent>
            </Card>
          ))}
          <Card>
            <CardHeader><CardTitle>Digital (sem cidade)</CardTitle><CardDescription>Operações digitais recebem identificação própria; nenhuma cidade é inventada.</CardDescription></CardHeader>
            <CardContent className="p-0 sm:p-2">{tableState(tableQuotes.filter((x) => x.city === null), true)}</CardContent>
          </Card>
        </TabsContent>
        <TabsContent value="simuladores">
          <Card>
            <CardHeader className="gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <CardTitle>Cotações dependentes do valor</CardTitle>
                <CardDescription>Cada linha preserva o contexto completo (origem, destino, pagamento, recebimento, banco, canal, promoção). Contextos diferentes nunca são misturados.</CardDescription>
              </div>
              <Filters value={filters} onChange={setFilters} showCapital={false} showAmount idPrefix="sim" />
            </CardHeader>
            <CardContent className="p-0 sm:p-2">
              {byAmount.isLoading ? (
                <TableSkeleton rows={4} cols={6} />
              ) : byAmount.isError ? (
                <ErrorState title="As simulações não carregaram" error={byAmount.error} onRetry={() => void byAmount.refetch()} />
              ) : simulatorQuotes.length === 0 ? (
                <EmptyState kind="no-match" compact title="Sem simulações para os filtros" description="Escolha outro montante, fonte ou moeda." />
              ) : (
                <Table scrollLabel="Simulações por montante (rola para o lado)">
                  <TableHeader>
                    <TableRow className="hover:bg-transparent">
                      <TableHead>Fonte</TableHead>
                      <TableHead>Montante</TableHead>
                      <TableHead>Recebimento</TableHead>
                      <TableHead>Pagamento</TableHead>
                      <TableHead className="text-right">Taxa efetiva</TableHead>
                      <TableHead>Promoção</TableHead>
                      <TableHead>Tarifas</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {simulatorQuotes.map((s) => (
                      <TableRow key={s.id}>
                        <TableCell className="font-medium">{srcName(s.source_id)}</TableCell>
                        <TableCell className="tnum">{formatMoney(s.amount_base, s.base)}</TableCell>
                        <TableCell>{s.context?.receive ? (RECEIVE_LABEL[s.context.receive] ?? s.context.receive) : "—"}</TableCell>
                        <TableCell>{s.context?.payment ? (PAYMENT_LABEL[s.context.payment] ?? s.context.payment) : "—"}</TableCell>
                        <TableCell className="tnum text-right">
                          {formatRateFixed(s.sell, s.quote)} <span className="text-muted">{s.quote}/{s.base}</span>
                        </TableCell>
                        <TableCell>{s.context?.promo ? <Badge variant="accent">{PROMO_LABEL[s.context.promo] ?? s.context.promo}</Badge> : <span className="text-muted">—</span>}</TableCell>
                        <TableCell className="text-xs text-muted">{s.fees.length ? s.fees.map(formatFee).join("; ") : "—"}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
      <div className="grid gap-4 xl:grid-cols-[3fr_2fr]">
        <Card className="min-w-0">
          <CardHeader>
            <CardTitle>Gráfico intradiário</CardTitle>
            <CardDescription>{chartQuote ? `${srcName(chartQuote.source_id)} · ${chartQuote.base}/${chartQuote.quote} · ${chartQuote.unit_note}` : "Selecione uma cotação na tabela"}</CardDescription>
          </CardHeader>
          <CardContent>
            {!chartQuote && !q.isLoading ? (
              <EmptyState kind="no-data" compact title="Sem cotação para traçar" description="Quando houver cotações para os filtros, o gráfico aparece aqui." />
            ) : hist.isLoading || !chartQuote ? (
              <Skeleton className="h-[260px]" />
            ) : hist.isError ? (
              <ErrorState title="O histórico não carregou" error={hist.error} onRetry={() => void hist.refetch()} />
            ) : (hist.data?.points.length ?? 0) === 0 ? (
              <EmptyState kind="no-data" compact title="Sem histórico para esta série" description="A série ainda não tem pontos nas últimas 24 h." />
            ) : (
              <PriceChart points={hist.data!.points} series={SERIES_ALL} height={260} quote={chartQuote.quote} pair={`${chartQuote.base}/${chartQuote.quote}`} reference={reference} watermark={mode === "demo" ? "DEMONSTRAÇÃO" : null} />
            )}
          </CardContent>
        </Card>
        {hist.data && hist.data.points.length > 0 && <VolatilityCard points={hist.data.points} />}
      </div>
    </div>
  );
}
