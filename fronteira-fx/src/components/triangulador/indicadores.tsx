"use client";
/**
 * Indicadores técnicos (RSI, MACD, estocástico, ADX, ATR, NATR, Ichimoku) de velas fechadas da Binance, em 5 min e
 * 1 dia. São leituras de mercado, com rótulo de referência: não são sinal de compra nem de venda.
 */
import * as React from "react";
import { Badge } from "@/components/ui/badge";
import { ErrorState } from "@/components/ui/error-state";
import { FxCard } from "@/components/ui/fx/fx-card";
import { FxSkeleton } from "@/components/ui/fx/fx-skeleton";
import { useIndicators } from "@/lib/queries";
import {
  INDICATOR_FIELDS,
  INSTRUMENTS,
  formatIndicator,
  type Indicators,
  type Instrument,
  type Interval,
} from "@/lib/api/triangulador";
import { CardGrid, SourceLine, Notice, Tag } from "./shared";

const INTERVAL_LABEL: Record<Interval, string> = { "5m": "5 minutos", "1d": "1 dia" };

function IndicatorCard({ instrument, interval }: { instrument: Instrument; interval: Interval }) {
  const q = useIndicators(instrument, interval);
  const id = `ind-${instrument.replace(/\W/g, "")}-${interval}`;
  return (
    <li className="min-w-0">
      <FxCard className="grid min-w-0 gap-3 p-4" data-testid="indicator-card" data-executable="false" data-instrument={instrument} data-interval={interval}>
        <article aria-labelledby={id} className="grid min-w-0 gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <h2 id={id} className="text-heading font-semibold">{instrument} · {INTERVAL_LABEL[interval]}</h2>
            <Tag executable={false} />
          </div>
          {q.isLoading ? (
            <div role="status" aria-label={`Carregando indicadores de ${instrument}`} className="grid gap-2">
              <span className="sr-only">Carregando…</span>
              <FxSkeleton className="h-24" />
            </div>
          ) : q.isError ? (
            <ErrorState compact title="Indicadores indisponíveis" error={q.error} onRetry={() => void q.refetch()} />
          ) : q.data ? (
            <IndicatorBody d={q.data} />
          ) : null}
        </article>
      </FxCard>
    </li>
  );
}

function IndicatorBody({ d }: { d: Indicators }) {
  if (d.status !== "ok") {
    return (
      <div className="grid gap-2">
        <Badge variant="incomplete">janela insuficiente</Badge>
        <p className="text-sm text-muted">Ainda não há velas fechadas suficientes ({d.closed_candles}) para calcular todos os indicadores.</p>
        <SourceLine source={d.source} at={d.as_of} label="Última vela fechada" />
      </div>
    );
  }
  return (
    <div className="grid min-w-0 gap-2">
      <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-sm tabular-nums sm:grid-cols-3">
        {INDICATOR_FIELDS.map(([key, name]) => (
          <div key={key} className="flex min-w-0 items-baseline justify-between gap-2 border-b border-border/60 py-1">
            <dt className="min-w-0 truncate text-xs text-muted">{name}</dt>
            <dd className="shrink-0 font-medium">{formatIndicator(d[key])}</dd>
          </div>
        ))}
      </dl>
      <SourceLine source={d.source} at={d.as_of} label="Última vela fechada" />
      <p className="text-xs text-muted">{d.note}</p>
    </div>
  );
}

export function Indicadores() {
  const intervals: Interval[] = ["5m", "1d"];
  return (
    <div className="grid min-w-0 gap-4">
      <p className="text-body text-muted">
        Indicadores técnicos calculados sobre velas fechadas. Servem para ler o mercado, não dão sinal de compra ou venda.
      </p>
      <Notice>Cálculo com a convenção TA-Lib. Valor «—» quer dizer que falta janela, nunca zero.</Notice>
      {INSTRUMENTS.map((inst) => (
        <section key={inst} aria-label={`Indicadores de ${inst}`} className="grid min-w-0 gap-3">
          <CardGrid label={`Indicadores de ${inst}`}>
            {intervals.map((iv) => (
              <IndicatorCard key={`${inst}-${iv}`} instrument={inst} interval={iv} />
            ))}
          </CardGrid>
        </section>
      ))}
    </div>
  );
}
