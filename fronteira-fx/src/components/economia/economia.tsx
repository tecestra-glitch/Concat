"use client";
/**
 * Economia e cripto (módulo market): manchetes de feeds públicos, referências de cripto e câmbio e a volatilidade
 * recente. Tudo é referência de mercado: nunca preço executável nem cotação de casa de câmbio.
 */
import * as React from "react";
import { PageHeader } from "@/components/shell/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import { useMarketNews, useMarketQuotes, useMarketVolatility } from "@/lib/queries";
import { useSettings } from "@/lib/settings";
import { NewsTimeline } from "./news-timeline";
import { ReferenceCards } from "./reference-cards";

export function Economia() {
  const { mode } = useSettings();
  const [source, setSource] = React.useState("all");
  const news = useMarketNews({ source, limit: 50 });
  const quotes = useMarketQuotes();
  const volatility = useMarketVolatility();
  const refsLoading = quotes.isLoading || volatility.isLoading;
  const refsError = (quotes.error ?? volatility.error) as Error | null;
  return (
    <div className="space-y-4">
      <PageHeader
        title="Economia e cripto"
        description="Manchetes de feeds públicos, cripto e câmbio de referência, e a volatilidade recente. Tudo aqui é referência de mercado: não é preço executável nem cotação de casa de câmbio."
      />
      {mode === "demo" && (
        <p className="text-xs text-warn">Demonstração: dados ilustrativos. Nenhum feed nem provedor é acessado.</p>
      )}
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
        <NewsTimeline
          items={news.data ?? []}
          loading={news.isLoading}
          error={news.error as Error | null}
          source={source}
          onSourceChange={setSource}
        />
        <div className="min-w-0 space-y-3">
          {refsLoading && <Skeleton className="h-64" />}
          {!refsLoading && refsError && (
            <p role="alert" className="text-sm text-loss">Falha ao carregar as referências: {refsError.message}</p>
          )}
          {!refsLoading && !refsError && (
            <ReferenceCards quotes={quotes.data ?? []} volatility={volatility.data ?? []} />
          )}
        </div>
      </div>
    </div>
  );
}
