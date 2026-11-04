"use client";
/**
 * Notícias e sentimento. O sentimento é o índice Fear & Greed (Alternative.me) do mercado como um todo, com a
 * atribuição visível. As manchetes vêm de feeds públicos: título e link, com a fonte e a data de cada uma. O texto
 * das manchetes é dado de terceiros e sai escapado, nunca como instrução. Nenhuma notícia recebe nota própria.
 */
import * as React from "react";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { FxCard } from "@/components/ui/fx/fx-card";
import { FxSkeleton } from "@/components/ui/fx/fx-skeleton";
import { useMarketNews, useSentiment } from "@/lib/queries";
import { MARKET_SOURCE_LABEL, type NewsItem } from "@/lib/api/market";
import { sentimentTone, type Sentiment } from "@/lib/api/triangulador";
import { formatDateTime } from "@/lib/format";
import { Notice, SourceLine, Tag } from "./shared";

const TONE_VARIANT = { loss: "loss", warn: "warn", neutral: "default", gain: "gain" } as const;

export function SentimentCard({ latest, history }: { latest: Sentiment; history: Sentiment[] }) {
  const tone = sentimentTone(latest.value);
  return (
    <FxCard className="grid min-w-0 gap-3 p-4" data-testid="sentiment-card" data-executable="false">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-heading font-semibold">Fear &amp; Greed do mercado</h2>
        <Tag executable={false} />
      </div>
      <div className="flex flex-wrap items-baseline gap-3">
        <span className="text-3xl font-semibold tabular-nums" data-testid="sentiment-value">{latest.value}</span>
        <Badge variant={TONE_VARIANT[tone]}>{latest.classification}</Badge>
      </div>
      {history.length > 1 && (
        <p className="break-words text-xs text-muted tabular-nums" aria-label="Últimas leituras">
          Últimas leituras: {history.slice(0, 7).map((h) => h.value).join(" · ")}
        </p>
      )}
      <SourceLine source={latest.provider} at={latest.observed_at} />
      <p className="break-words text-xs text-muted">{latest.attribution}</p>
    </FxCard>
  );
}

export function NewsRow({ item }: { item: NewsItem }) {
  return (
    <li className="grid min-w-0 gap-1.5 border-b border-border/60 py-3 last:border-b-0" data-testid="news-item">
      <a
        href={item.link}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex min-h-11 min-w-0 items-center break-words text-body font-medium text-accent-strong underline-offset-2 hover:underline"
      >
        {item.title}
        <span className="sr-only"> (abre em nova aba)</span>
      </a>
      {item.excerpt && <p className="break-words text-xs text-muted">{item.excerpt}</p>}
      <p className="break-words text-xs text-muted">
        Fonte: <span className="text-foreground">{MARKET_SOURCE_LABEL[item.source] ?? item.source}</span>
        {item.published_at ? ` · publicada ${formatDateTime(item.published_at)}` : ""}
      </p>
      <p className="break-words text-xs text-muted" data-testid="news-attribution">{item.attribution}</p>
    </li>
  );
}

export function Noticias() {
  const sent = useSentiment(30);
  const news = useMarketNews({ limit: 30 });
  const latest = sent.data?.[0];

  return (
    <div className="grid min-w-0 gap-4">
      <p className="text-body text-muted">
        Manchetes de feeds públicos com a fonte e a data de cada uma, e o sentimento do mercado. Notícia não recebe nota
        de sentimento: o índice vale para o mercado todo.
      </p>
      <Notice>Os textos são de terceiros: leia a fonte pelo link. Nada aqui é recomendação.</Notice>

      <section aria-labelledby="n-sent" className="grid min-w-0 gap-3">
        <h2 id="n-sent" className="sr-only">Sentimento de mercado</h2>
        {sent.isLoading ? (
          <div role="status" aria-label="Carregando sentimento" className="grid gap-2">
            <span className="sr-only">Carregando…</span>
            <FxSkeleton className="h-36" />
          </div>
        ) : sent.isError ? (
          <ErrorState compact title="O sentimento não carregou" error={sent.error} onRetry={() => void sent.refetch()} />
        ) : latest ? (
          <SentimentCard latest={latest} history={sent.data ?? []} />
        ) : (
          <EmptyState kind="no-data" title="Sem sentimento de mercado" description="Nenhuma leitura do índice chegou ainda." />
        )}
      </section>

      <section aria-labelledby="n-news" className="grid min-w-0 gap-3">
        <h2 id="n-news" className="text-heading font-semibold">Manchetes</h2>
        {news.isLoading ? (
          <div role="status" aria-label="Carregando notícias" className="grid gap-2">
            <span className="sr-only">Carregando…</span>
            <FxSkeleton className="h-24" />
            <FxSkeleton className="h-24" />
          </div>
        ) : news.isError ? (
          <ErrorState title="As notícias não carregaram" error={news.error} onRetry={() => void news.refetch()} />
        ) : (news.data ?? []).length === 0 ? (
          <EmptyState kind="no-data" title="Sem manchetes" description="Nenhum feed trouxe manchete recente." />
        ) : (
          <ul aria-label="Manchetes" className="min-w-0">
            {(news.data ?? []).map((n) => (
              <NewsRow key={n.id} item={n} />
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
