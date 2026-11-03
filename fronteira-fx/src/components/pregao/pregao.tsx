"use client";
/**
 * Tela de pregão (§24.4): liga hooks, preferências e atalhos às folhas de `src/components/pregao/*`.
 * Panorama das cotações publicadas pelas casas; não é bolsa e nada aqui executa operação. BCP e
 * dolarPy aparecem só como referência. Em demo, cotações, velas e atualizações vêm dos geradores
 * locais (sem rede) e a tela leva a nota de demonstração além da faixa global.
 */
import * as React from "react";
import dynamic from "next/dynamic";
import { PageHeader } from "@/components/shell/page-header";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useSettings } from "@/lib/settings";
import { useNow } from "@/lib/use-now";
import { pairKeyOf, quoteOfPair } from "@/lib/pregao/candles";
import { toHeatCells, toTickerItems, toWatchlistRows } from "@/lib/pregao/derive";
import { buildOverlays } from "@/lib/pregao/indicators";
import { updatePregaoPrefs, usePregaoPrefs } from "@/lib/pregao/prefs";
import type { HouseSession, IndicatorState, PairKey, Timeframe } from "@/lib/pregao/types";
import { useCandles, useSparklines } from "@/lib/pregao/use-candles";
import { buildPregaoBindings, useHotkeys } from "@/lib/pregao/use-hotkeys";
import { useHouseSessions } from "@/lib/pregao/use-house-sessions";
import { usePregaoQuotes } from "@/lib/pregao/use-pregao-quotes";
import { usePrintsFeed, usePrintsFor } from "@/lib/pregao/use-prints";
import { statsByKey, useSessionStats } from "@/lib/pregao/use-session-stats";
import { buildPregaoView, cyclePair } from "@/lib/pregao/view";
import { BookLadder } from "./book-ladder";
import { CrossRateCard } from "./cross-rate-card";
import { IndicatorToggles } from "./indicator-toggles";
import { LatestPrints } from "./latest-prints";
import { MarketStatus } from "./market-status";
import { PairSelector } from "./pair-selector";
import { PregaoLayout } from "./pregao-layout";
import { SessionClock } from "./session-clock";
import { ShortcutsHelp } from "./shortcuts-help";
import { SpreadHeatmap } from "./spread-heatmap";
import { StatsStrip } from "./stats-strip";
import { TickerTape } from "./ticker-tape";
import { TimeframeBar } from "./timeframe-bar";
import { Watchlist } from "./watchlist";

/** O canvas do lightweight-charts só existe no cliente; o esqueleto ocupa o slot enquanto carrega. */
const CandleChart = dynamic(() => import("@/components/pregao/candle-chart").then((m) => m.CandleChart), {
  ssr: false,
  loading: () => (
    <div data-testid="pregao-chart" data-state="loading" aria-busy="true" className="h-full">
      <Skeleton className="h-full w-full" />
      <span className="sr-only">Carregando…</span>
    </div>
  ),
});

const NO_SESSIONS: HouseSession[] = [];
const PRINTS_LIMIT = 30;
const SPARK_COUNT = 24;

/**
 * Estado de um painel cuja consulta depende das cotações (resumo e gráfico): enquanto as cotações
 * carregam não há chave e a consulta própria fica desligada, mas o painel continua "carregando";
 * se as cotações falham, o painel mostra esse erro e a nova tentativa vai para as cotações.
 */
export function remotePanel(
  own: { isLoading: boolean; data: unknown; error: Error | null },
  upstream: { loading: boolean; error: Error | null },
): { loading: boolean; error: Error | null; retryUpstream: boolean } {
  const ownError = own.data !== undefined ? null : own.error;
  const error = ownError ?? (own.data !== undefined ? null : upstream.error);
  return { loading: upstream.loading || own.isLoading, error, retryUpstream: ownError === null && error !== null };
}

const setTimeframe = (tf: Timeframe) => updatePregaoPrefs({ tf });
const setIndicators = (indicators: IndicatorState) => updatePregaoPrefs({ indicators });

export function Pregao() {
  const { mode } = useSettings();
  const now = useNow();
  const prefs = usePregaoPrefs();
  const [pair, setPair] = React.useState<PairKey>("USD/PYG");
  const [selectedKey, setSelectedKey] = React.useState<string | null>(null);
  const [helpOpen, setHelpOpen] = React.useState(false);
  usePrintsFeed();

  const tf = prefs.tf;
  const indicators = prefs.indicators;
  const ready = now !== 0;
  const demo = mode === "demo";
  const nowDate = React.useMemo(() => new Date(now), [now]);

  // Em demo as cotações vêm recarimbadas com o relógio da tela (idade e status fazem sentido).
  const quotesQ = usePregaoQuotes(now);
  const { quotes, sources } = quotesQ;
  const sessionsQ = useHouseSessions();
  const sessions = sessionsQ.data ?? NO_SESSIONS;

  const view = React.useMemo(
    () => buildPregaoView({ quotes, sources, sessions, pair, selectedKey, now: nowDate }),
    [quotes, sources, sessions, pair, selectedKey, nowDate],
  );
  const { levels, allLevels, allKeys, houseKeys, effectiveKey, selectedLevel, heatHouses, reference, cross, referenceNext } = view;

  const statsQ = useSessionStats(allKeys);
  const byKey = React.useMemo(() => statsByKey(statsQ.data), [statsQ.data]);
  // Na troca de par ou de casa não há placeholder (a consulta fica carregando); na troca de intervalo, as velas
  // anteriores ficam até chegar a série nova (`candlesQueryOptions`, QA-3).
  const candlesQ = useCandles(effectiveKey, tf);
  const sparks = useSparklines(houseKeys, SPARK_COUNT);
  const allPrints = usePrintsFor(mode, PRINTS_LIMIT);

  const overlays = React.useMemo(() => buildOverlays(candlesQ.data?.candles ?? [], indicators), [candlesQ.data, indicators]);
  const rows = React.useMemo(() => toWatchlistRows(levels, byKey, sparks), [levels, byKey, sparks]);
  const ticker = React.useMemo(() => toTickerItems(quotes, sources, byKey), [quotes, sources, byKey]);
  const heat = React.useMemo(() => toHeatCells(allLevels), [allLevels]);
  // Modos nunca se misturam: o store de atualizações é do módulo e sobrevive à troca de modo.
  const prints = React.useMemo(() => allPrints.filter((p) => p.data_mode === mode), [allPrints, mode]);
  const stats = effectiveKey ? (byKey.get(effectiveKey) ?? null) : null;
  const quote = quoteOfPair(pair);

  const quotesLoading = !ready || quotesQ.isPending;
  const quotesError = quotesQ.error;
  const upstream = { loading: quotesLoading, error: quotesError };
  const statsPanel = remotePanel(statsQ, upstream);
  const chartPanel = remotePanel(candlesQ, upstream);

  const choosePair = (p: PairKey) => {
    setPair(p);
    setSelectedKey(null);
  };
  const onSelect = (key: string) => {
    const pk = pairKeyOf(key);
    if (pk && pk !== pair) setPair(pk);
    setSelectedKey(key);
  };
  const toggleHelp = () => setHelpOpen((o) => !o);

  const bindings = React.useMemo(
    () =>
      buildPregaoBindings({
        setTimeframe,
        cyclePair: (dir) => {
          setPair((p) => cyclePair(p, dir));
          setSelectedKey(null);
        },
        toggleHelp: () => setHelpOpen((o) => !o),
        escape: () => {
          if (helpOpen) setHelpOpen(false);
          else setSelectedKey(null);
        },
      }),
    [helpOpen],
  );
  useHotkeys(bindings, true);

  return (
    <div data-testid="pregao-root" data-mode={mode}>
      <PageHeader title="Pregão" description="Cotações publicadas pelas casas de câmbio. Referências do BCP só para comparar.">
        <Button type="button" variant="outline" size="sm" onClick={toggleHelp}>
          Atalhos <kbd className="tnum ml-1 rounded border border-border px-1 text-xs">?</kbd>
        </Button>
      </PageHeader>
      <PregaoLayout
        banner={
          demo ? (
            <p role="note" data-testid="pregao-demo-note" className="rounded-md border border-dashed border-border bg-surface px-3 py-2 text-xs text-muted">
              Demonstração: velas, livro e atualizações são gerados localmente e não refletem o mercado.
            </p>
          ) : null
        }
        ticker={<TickerTape items={ticker} selectedKey={effectiveKey} onSelect={onSelect} loading={quotesLoading} />}
        controls={
          <div className="flex flex-wrap items-center gap-2">
            <TimeframeBar value={tf} onChange={setTimeframe} />
            <PairSelector value={pair} onChange={choosePair} />
            <IndicatorToggles value={indicators} onChange={setIndicators} />
          </div>
        }
        stats={
          <StatsStrip
            stats={stats}
            quote={quote}
            now={now}
            loading={statsPanel.loading}
            error={statsPanel.error}
            onRetry={statsPanel.retryUpstream ? quotesQ.refetch : () => void statsQ.refetch()}
          />
        }
        chart={
          <CandleChart
            series={candlesQ.data ?? null}
            timeframe={tf}
            quote={quote}
            indicators={indicators}
            overlays={overlays}
            house={selectedLevel?.house}
            reference={reference}
            demo={demo}
            loading={chartPanel.loading}
            error={chartPanel.error}
            onRetry={chartPanel.retryUpstream ? quotesQ.refetch : () => void candlesQ.refetch()}
          />
        }
        book={
          <BookLadder
            levels={levels}
            pair={pair}
            quote={quote}
            selectedKey={effectiveKey}
            onSelect={onSelect}
            now={now}
            loading={quotesLoading}
            error={quotesError}
            onRetry={quotesQ.refetch}
          />
        }
        bookExtra={
          <div className="grid grid-cols-1 gap-4">
            <section aria-labelledby="pregao-h-mapa" className="grid grid-cols-1 gap-2">
              <h3 id="pregao-h-mapa" className="text-sm font-medium">
                Mapa de spread
              </h3>
              <SpreadHeatmap cells={heat} houses={heatHouses} selectedKey={effectiveKey} onSelect={onSelect} loading={quotesLoading} />
            </section>
            <CrossRateCard house={cross.house} usdPyg={cross.usdPyg} usdBrl={cross.usdBrl} direct={cross.direct} now={now} />
          </div>
        }
        prints={<LatestPrints prints={prints} limit={PRINTS_LIMIT} onSelect={onSelect} loading={!ready} className="xl:min-h-0 xl:flex-1" />}
        watchlist={<Watchlist rows={rows} selectedKey={effectiveKey} onSelect={onSelect} loading={quotesLoading} error={quotesError} onRetry={quotesQ.refetch} />}
        clocks={
          <div className="flex flex-wrap items-center gap-3">
            <SessionClock now={now} referenceNext={referenceNext} />
            <MarketStatus sessions={sessions} now={now} />
          </div>
        }
      />
      <ShortcutsHelp open={helpOpen} onOpenChange={setHelpOpen} bindings={bindings} />
    </div>
  );
}
