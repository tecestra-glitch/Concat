"use client";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatDateTime } from "@/lib/format";
import { REFERENCE_NOTE, type MarketQuote, type MarketVolatility } from "@/lib/api/market";
import { changeTone, formatChangePct, formatReference, formatVolPct, volatilityView } from "./economia-helpers";

const TONE_CLASS = { gain: "text-gain-strong", loss: "text-loss", muted: "text-muted" } as const;

function VolatilityDetail({ v }: { v: MarketVolatility }) {
  const view = volatilityView(v);
  return (
    <div className="space-y-2" data-testid="volatility-detail" data-instrument={v.instrument} data-regime={v.regime ?? v.status}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs text-muted">Volatilidade</span>
        <Badge variant={view.variant} title={view.description} aria-label={`Volatilidade ${view.label}. ${view.description}`}>
          {view.label}
        </Badge>
        {v.alert && <Badge variant="loss">alerta</Badge>}
      </div>
      {v.status === "ok" && (
        <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs tabular-nums">
          <dt className="text-muted" title="Último retorno de 5 minutos">Movimento 5 min</dt>
          <dd className="whitespace-nowrap text-right">{formatVolPct(v.last_move_pct)}</dd>
          <dt className="text-muted" title="Desvio previsto do próximo movimento de 5 minutos (EWMA, λ = 0,94)">Desvio 5 min</dt>
          <dd className="whitespace-nowrap text-right">{formatVolPct(v.ewma_pct_5m)}</dd>
          <dt className="text-muted" title="Volatilidade de 1 dia, Parkinson das velas de 5 min">Vol. 1 dia</dt>
          <dd className="whitespace-nowrap text-right">{formatVolPct(v.parkinson_1d_pct)}</dd>
          <dt className="text-muted" title="Volatilidade de 20 dias, Parkinson das velas diárias">Vol. 20 dias</dt>
          <dd className="whitespace-nowrap text-right">{formatVolPct(v.parkinson_20d_pct)}</dd>
          <dt className="text-muted" title="Average True Range de 14 velas de 5 min, em preço">ATR(14)</dt>
          <dd className="whitespace-nowrap text-right">{formatReference(v.atr_14_5m)}</dd>
        </dl>
      )}
    </div>
  );
}

function QuoteCard({ q, vol }: { q: MarketQuote; vol: MarketVolatility | undefined }) {
  const tone = changeTone(q.change_pct);
  return (
    <Card data-testid="reference-card" data-instrument={q.instrument} className="flex flex-col">
      <CardHeader className="gap-1">
        <div className="flex flex-wrap items-center gap-2">
          <CardTitle className="text-sm">{q.instrument}</CardTitle>
          <Badge variant="reference">referência</Badge>
        </div>
        <CardDescription className="break-words">{q.label}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col gap-3">
        <div className="flex flex-wrap items-baseline gap-x-3">
          <span className="text-2xl font-semibold tabular-nums" data-testid="reference-price">{formatReference(q.price)}</span>
          <span className={`text-sm font-medium tabular-nums ${TONE_CLASS[tone]}`} data-testid="reference-change">{formatChangePct(q.change_pct)}</span>
        </div>
        <p className="text-xs text-muted">Observado em {formatDateTime(q.observed_at)}</p>
        {vol && <VolatilityDetail v={vol} />}
      </CardContent>
    </Card>
  );
}

const GROUPS: { kind: MarketQuote["kind"]; title: string; description: string }[] = [
  { kind: "crypto", title: "Cripto", description: "Binance, dados públicos. Volatilidade calculada sobre velas de 5 min e diárias." },
  { kind: "fx_reference", title: "Câmbio de referência", description: "Frankfurter (dados do BCE), diário. Não é a cotação das casas de câmbio." },
  { kind: "bcb_series", title: "Banco Central", description: "PTAX e Selic meta, séries oficiais do SGS." },
];

export function ReferenceCards({ quotes, volatility }: { quotes: MarketQuote[]; volatility: MarketVolatility[] }) {
  const volBy = new Map(volatility.map((v) => [v.instrument, v]));
  return (
    <section aria-labelledby="economia-referencias" className="space-y-3">
      <h3 id="economia-referencias" className="sr-only">Referências de mercado</h3>
      <p role="note" className="rounded-md border border-dashed border-border-strong px-3 py-2 text-xs text-muted">
        {REFERENCE_NOTE}
      </p>
      {GROUPS.map((g) => {
        const rows = quotes.filter((q) => q.kind === g.kind);
        if (rows.length === 0) return null;
        return (
          <div key={g.kind} className="space-y-2" data-testid="reference-group" data-kind={g.kind}>
            <div>
              <h4 className="text-sm font-semibold">{g.title}</h4>
              <p className="text-xs text-muted">{g.description}</p>
            </div>
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {rows.map((q) => (
                <QuoteCard key={q.instrument} q={q} vol={volBy.get(q.instrument)} />
              ))}
            </div>
          </div>
        );
      })}
    </section>
  );
}
