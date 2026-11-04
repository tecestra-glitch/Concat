"use client";
/**
 * Melhores oportunidades da home (dev/ui/spec-reforma-ui.md, seção 5a): top 5 do ranking principal, com o primeiro
 * item em `fx-card` (cartao-hover) e o fundo em `fx-grid` (padrao-grade). Confiança e "não confirmado" usam as mesmas
 * células do ranking, para nunca mostrar custo incompleto como lucro confirmado.
 */
import * as React from "react";
import Link from "next/link";
import { ConfidenceBadge, GainCell, formatPercentPlain, routeCurrencies } from "@/components/opportunities/ranking-table";
import { Button } from "@/components/ui/button";
import { CurrencyFlag } from "@/components/ui/currency-flag";
import { Delta } from "@/components/ui/delta";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { FxCard } from "@/components/ui/fx/fx-card";
import { FxGrid } from "@/components/ui/fx/fx-grid";
import { FxSkeleton } from "@/components/ui/fx/fx-skeleton";
import { formatMoney } from "@/lib/format";
import { useOpportunities } from "@/lib/queries";
import type { Opportunity } from "@/lib/api/types";
import { useSettings } from "@/lib/settings";

export const HOME_TOP = 5;

export function HomeOpportunities() {
  const { settings } = useSettings();
  const opps = useOpportunities({ capital: settings.defaultCapital });
  const top = (opps.data ?? []).filter((o) => o.in_main_ranking).slice(0, HOME_TOP);

  return (
    <section aria-labelledby="home-h-oport" data-testid="home-opportunities" className="relative isolate min-w-0 overflow-hidden rounded-surface border border-border bg-surface p-4 shadow-[var(--shadow-1)]">
      <FxGrid />
      <div className="relative grid gap-3">
        <div className="flex items-end justify-between gap-2">
          <div className="min-w-0">
            <h2 id="home-h-oport" className="text-heading font-semibold">Melhores oportunidades</h2>
            <p className="text-caption text-muted">Ranking principal para o orçamento de {formatMoney(settings.defaultCapital, "BRL")}.</p>
          </div>
          <Button asChild variant="ghost" size="sm" className="shrink-0">
            <Link href="/oportunidades">Ver todas</Link>
          </Button>
        </div>

        {opps.isLoading ? (
          <div className="grid gap-2" role="status" aria-label="Carregando oportunidades">
            <span className="sr-only">Carregando…</span>
            {Array.from({ length: 4 }, (_, i) => (
              <FxSkeleton key={i} className="h-14" />
            ))}
          </div>
        ) : opps.isError ? (
          <ErrorState compact title="O ranking não carregou" error={opps.error} onRetry={() => void opps.refetch()} />
        ) : top.length === 0 ? (
          <EmptyState compact kind="no-data" title="Nenhuma oportunidade no ranking principal" description="Quando uma rota passar nos critérios, ela aparece aqui." />
        ) : (
          <ol className="grid gap-2">
            {top.map((o, i) =>
              i === 0 ? (
                <li key={o.id}>
                  <FxCard className="p-0" data-testid="home-opportunity-featured">
                    <OpportunityRow o={o} rank={1} />
                  </FxCard>
                </li>
              ) : (
                <li key={o.id} className="rounded-control border border-border bg-background/60" data-testid="home-opportunity">
                  <OpportunityRow o={o} rank={i + 1} />
                </li>
              ),
            )}
          </ol>
        )}
      </div>
    </section>
  );
}

function OpportunityRow({ o, rank }: { o: Opportunity; rank: number }) {
  return (
    <div className="grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3 px-3 py-2.5">
      <span className="fx-tnum w-5 text-muted">{rank}</span>
      <div className="min-w-0">
        <div className="truncate text-body font-medium">{o.title}</div>
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-caption text-muted">
          <span className="flex min-w-0 flex-wrap items-center gap-1">
            {routeCurrencies(o).map((c, i) => (
              <React.Fragment key={`${c}-${i}`}>
                {i > 0 && <span aria-hidden>→</span>}
                <CurrencyFlag code={c} />
              </React.Fragment>
            ))}
          </span>
          <span>capital {formatMoney(o.capital_brl, "BRL")}</span>
        </div>
      </div>
      <div className="grid justify-items-end gap-1 text-right">
        <span className="text-body"><GainCell o={o} /></span>
        <span className="fx-num text-caption">
          {o.confidence === "incomplete" ? <span className="text-muted">≈ {formatPercentPlain(o.roi)}</span> : <Delta value={o.roi} />}
        </span>
        <ConfidenceBadge c={o.confidence} />
      </div>
    </div>
  );
}
