"use client";
/**
 * Mercado global: câmbio (Frankfurter, PTAX, Open Exchange Rates), índices (dólar amplo do FRED) e cripto (Binance,
 * dados públicos). Tudo é referência: nenhum número desta tela é preço executável nem cotação de casa de câmbio.
 */
import * as React from "react";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { FxCard } from "@/components/ui/fx/fx-card";
import { FxSkeleton } from "@/components/ui/fx/fx-skeleton";
import { useCryptoRefs, useFxRefs, useMacroRefs } from "@/lib/queries";
import type { ReferenceQuote, FxReference } from "@/lib/api/triangulador";
import { formatChangePctText, formatReferencePrice, referenceKindLabel } from "@/lib/api/triangulador";
import { CardGrid, SourceLine, Notice, Tag } from "./shared";

function QuoteCard({ q }: { q: ReferenceQuote }) {
  return (
    <li className="min-w-0">
      <FxCard className="grid min-w-0 gap-2 p-4" data-testid="global-card" data-executable="false">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-semibold break-all">{q.instrument}</span>
          <Tag executable={false} />
          <Badge variant="outline">{referenceKindLabel(q.kind, q.source)}</Badge>
        </div>
        <p className="break-words text-xs text-muted">{q.label}</p>
        <div className="flex flex-wrap items-baseline gap-x-3">
          <span className="text-2xl font-semibold tabular-nums" data-testid="global-price">{formatReferencePrice(q.price)}</span>
          <span className="text-sm tabular-nums text-muted">{formatChangePctText(q.change_pct)}</span>
        </div>
        <SourceLine source={q.source} at={q.observed_at} />
      </FxCard>
    </li>
  );
}

function FxCardItem({ r }: { r: FxReference }) {
  return (
    <li className="min-w-0">
      <FxCard className="grid min-w-0 gap-2 p-4" data-testid="global-card" data-executable="false">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-semibold break-all">{r.instrument}</span>
          <Tag executable={false} />
          <Badge variant="outline">Câmbio de referência</Badge>
        </div>
        <span className="text-2xl font-semibold tabular-nums" data-testid="global-price">{formatReferencePrice(r.price)}</span>
        <SourceLine source={r.source} at={r.observed_at} label="Observado" />
        <p className="text-xs text-muted">Coletado em {r.collected_at ? new Date(r.collected_at).toLocaleString("pt-BR") : "—"}. Não serve para transação.</p>
      </FxCard>
    </li>
  );
}

function Section({ id, title, description, children }: { id: string; title: string; description: string; children: React.ReactNode }) {
  return (
    <section aria-labelledby={id} className="grid min-w-0 gap-3">
      <div className="min-w-0">
        <h2 id={id} className="text-heading font-semibold">{title}</h2>
        <p className="text-caption text-muted">{description}</p>
      </div>
      {children}
    </section>
  );
}

function Loading({ label }: { label: string }) {
  return (
    <div role="status" aria-label={`Carregando ${label}`} className="grid gap-3 sm:grid-cols-2">
      <span className="sr-only">Carregando…</span>
      <FxSkeleton className="h-36" />
      <FxSkeleton className="h-36" />
    </div>
  );
}

export function MercadoGlobal() {
  const fx = useFxRefs();
  const macro = useMacroRefs();
  const crypto = useCryptoRefs();
  const indices = (macro.data ?? []).filter((q) => q.source === "fred");
  const bcb = (macro.data ?? []).filter((q) => q.source !== "fred");

  return (
    <div className="grid min-w-0 gap-6">
      <p className="text-body text-muted">
        Câmbio, índices e cripto de referência. Nada aqui é preço de casa de câmbio nem executável: serve para comparar,
        não para operar.
      </p>
      <Notice>Referências: câmbio (Frankfurter, PTAX, Open Exchange Rates), índice (FRED) e cripto (Binance, dados públicos).</Notice>

      <Section id="g-fx" title="Câmbio de referência" description="Taxas diárias de fontes oficiais e agregadores. Sempre não executáveis.">
        {fx.isLoading ? (
          <Loading label="câmbio" />
        ) : fx.isError ? (
          <ErrorState title="O câmbio de referência não carregou" error={fx.error} onRetry={() => void fx.refetch()} />
        ) : (fx.data ?? []).length === 0 ? (
          <EmptyState kind="no-data" title="Sem câmbio de referência" description="Nenhuma coleta de câmbio de referência chegou ainda." />
        ) : (
          <CardGrid label="Câmbio de referência">
            {(fx.data ?? []).map((r, i) => (
              <FxCardItem key={`${r.source}-${r.instrument}-${i}`} r={r} />
            ))}
          </CardGrid>
        )}
      </Section>

      <Section id="g-idx" title="Índices" description="Dólar amplo do FRED (DTWEXBGS). É uma aproximação, não é o DXY.">
        {macro.isLoading ? (
          <Loading label="índices" />
        ) : macro.isError ? (
          <ErrorState title="Os índices não carregaram" error={macro.error} onRetry={() => void macro.refetch()} />
        ) : indices.length === 0 ? (
          <EmptyState kind="no-data" title="Sem índices" description="Nenhum índice coletado ainda." />
        ) : (
          <CardGrid label="Índices">
            {indices.map((q) => (
              <QuoteCard key={q.instrument} q={q} />
            ))}
          </CardGrid>
        )}
      </Section>

      <Section id="g-bcb" title="Séries do Banco Central" description="Selic, IPCA e PTAX do SGS. Referência, não cotação.">
        {macro.isLoading ? (
          <Loading label="séries" />
        ) : macro.isError ? null : bcb.length === 0 ? (
          <EmptyState kind="no-data" title="Sem séries do BCB" description="Nenhuma série do SGS coletada ainda." />
        ) : (
          <CardGrid label="Séries do Banco Central">
            {bcb.map((q) => (
              <QuoteCard key={q.instrument} q={q} />
            ))}
          </CardGrid>
        )}
      </Section>

      <Section id="g-cry" title="Cripto" description="Cotações públicas da Binance. Referência de mercado: não é preço executável.">
        {crypto.isLoading ? (
          <Loading label="cripto" />
        ) : crypto.isError ? (
          <ErrorState title="A cripto não carregou" error={crypto.error} onRetry={() => void crypto.refetch()} />
        ) : (crypto.data ?? []).length === 0 ? (
          <EmptyState kind="no-data" title="Sem cotações de cripto" description="Nenhuma cotação de cripto coletada ainda." />
        ) : (
          <CardGrid label="Cripto de referência">
            {(crypto.data ?? []).map((q) => (
              <QuoteCard key={q.instrument} q={q} />
            ))}
          </CardGrid>
        )}
      </Section>
    </div>
  );
}
