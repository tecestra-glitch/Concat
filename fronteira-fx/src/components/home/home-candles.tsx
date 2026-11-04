"use client";
/**
 * Painel de velas da home (dev/ui/spec-reforma-ui.md, seção 5a). Reaproveita o `CandleChart` do pregão com o prefixo
 * de teste `home`, o mesmo pipeline de dados (cotações, sessões, velas). Os três números (último, variação, spread
 * médio) saem das velas e do livro; nada é animado sobre o número.
 */
import * as React from "react";
import { CandleChart } from "@/components/pregao/candle-chart";
import { PairSelector } from "@/components/pregao/pair-selector";
import { Delta } from "@/components/ui/delta";
import { ErrorState } from "@/components/ui/error-state";
import { PairFlags, type FlagCode } from "@/components/ui/currency-flag";
import { Skeleton } from "@/components/ui/skeleton";
import { formatRate, toNumber } from "@/lib/format";
import { quoteOfPair } from "@/lib/pregao/candles";
import { buildOverlays } from "@/lib/pregao/indicators";
import { usePregaoPrefs } from "@/lib/pregao/prefs";
import type { HouseSession, PairKey } from "@/lib/pregao/types";
import { useCandles } from "@/lib/pregao/use-candles";
import { useHouseSessions } from "@/lib/pregao/use-house-sessions";
import { usePregaoQuotes } from "@/lib/pregao/use-pregao-quotes";
import { buildPregaoView } from "@/lib/pregao/view";
import { useSettings } from "@/lib/settings";
import { useNow } from "@/lib/use-now";

const NO_SESSIONS: HouseSession[] = [];

export function HomeCandles({ pair, onPairChange }: { pair: PairKey; onPairChange: (p: PairKey) => void }) {
  const { mode } = useSettings();
  const now = useNow();
  const prefs = usePregaoPrefs();
  const nowDate = React.useMemo(() => new Date(now), [now]);
  const quotesQ = usePregaoQuotes(now);
  const sessionsQ = useHouseSessions();
  const view = React.useMemo(
    () => buildPregaoView({ quotes: quotesQ.quotes, sources: quotesQ.sources, sessions: sessionsQ.data ?? NO_SESSIONS, pair, selectedKey: null, now: nowDate }),
    [quotesQ.quotes, quotesQ.sources, sessionsQ.data, pair, nowDate],
  );
  const candlesQ = useCandles(view.effectiveKey, prefs.tf);
  const candles = candlesQ.data?.candles;
  const overlays = React.useMemo(() => buildOverlays(candles ?? [], prefs.indicators), [candles, prefs.indicators]);
  const quote = quoteOfPair(pair);
  const [baseCode, quoteCode] = pair.split("/") as [FlagCode, FlagCode];

  const last = candles?.at(-1) ?? null;
  const first = candles?.[0] ?? null;
  const lastClose = toNumber(last?.c);
  const firstOpen = toNumber(first?.o);
  const change = lastClose !== null && firstOpen !== null && firstOpen > 0 ? (lastClose - firstOpen) / firstOpen : null;
  const spreads = view.levels.map((l) => l.spread_pct).filter((v): v is number => v !== null);
  const spreadAvg = spreads.length ? spreads.reduce((a, b) => a + b, 0) / spreads.length : null;

  const loading = quotesQ.isPending || candlesQ.isPending;
  const error = quotesQ.error ?? candlesQ.error;
  const chartBox = "h-(--panel-h-sm) md:h-(--panel-h-md) xl:h-(--panel-h-lg)";

  return (
    <section aria-labelledby="home-h-candles" data-testid="home-candles" className="min-w-0 space-y-3">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="grid gap-2">
          <h2 id="home-h-candles" className="flex flex-wrap items-center gap-2 text-heading font-semibold">
            Candles · <PairFlags base={baseCode} quote={quoteCode} />
          </h2>
          <PairSelector value={pair} onChange={onPairChange} />
        </div>
        <dl className="grid grid-cols-3 gap-x-5 text-caption text-muted" data-testid="home-numbers">
          <div className="grid justify-items-end">
            <dt>Último</dt>
            <dd className="fx-num text-body font-medium text-foreground" data-testid="home-last">{lastClose !== null ? formatRate(lastClose, quote) : "—"}</dd>
          </div>
          <div className="grid justify-items-end">
            <dt>Variação</dt>
            <dd className="text-body" data-testid="home-change">
              <Delta value={change} />
            </dd>
          </div>
          <div className="grid justify-items-end">
            <dt>Spread médio</dt>
            <dd className="fx-num text-body font-medium text-foreground" data-testid="home-spread">
              {spreadAvg !== null ? `${spreadAvg.toLocaleString("pt-BR", { maximumFractionDigits: 2 })} %` : "—"}
            </dd>
          </div>
        </dl>
      </div>

      {error && !candles ? (
        <ErrorState title="As velas não carregaram" error={error} onRetry={() => void quotesQ.refetch()} />
      ) : loading && !candles ? (
        <Skeleton className={chartBox} />
      ) : (
        <div className={chartBox}>
          <CandleChart
            testIdPrefix="home"
            series={candlesQ.data ?? null}
            timeframe={prefs.tf}
            quote={quote}
            indicators={prefs.indicators}
            overlays={overlays}
            house={view.selectedLevel?.house}
            reference={view.reference}
            demo={mode === "demo"}
            loading={loading}
            error={candlesQ.error}
            onRetry={() => void candlesQ.refetch()}
          />
        </div>
      )}
    </section>
  );
}
