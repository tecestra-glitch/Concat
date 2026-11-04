"use client";
import type { ReactElement } from "react";
import { TriangleAlert } from "lucide-react";
import type { Currency } from "@/lib/api/types";
import { Delta } from "@/components/pregao/delta";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { formatAge, formatPercent, formatRate, toNumber } from "@/lib/format";
import type { SessionStats } from "@/lib/pregao/types";
import { cn } from "@/lib/utils";

/** Acima disso a última atualização vira aviso no tile "Último" (§18.2). */
export const STALE_AFTER_MS = 15 * 60_000;

const DASH = "—";
const TILE_COUNT = 8;

export interface StatsCell {
  id: "open" | "high" | "low" | "last" | "change" | "range" | "quotes" | "spread";
  label: string;
  value: string;
  deltaAbs?: number | null;
  deltaPct?: number | null;
  sub?: string;
  warn?: string;
}

export interface StatsStripProps {
  stats: SessionStats | null;
  quote: Currency;
  /** Epoch em ms; `0` no servidor (idades ficam ocultas). */
  now: number;
  loading?: boolean;
  error?: Error | null;
  onRetry?: () => void;
  className?: string;
}

/** Posição 0–100 da última cotação na faixa mín–máx; `null` se faltar valor ou a faixa for nula. */
export function rangePosition(low: string | null, high: string | null, last: string | null): number | null {
  const lo = toNumber(low);
  const hi = toNumber(high);
  const la = toNumber(last);
  if (lo === null || hi === null || la === null || hi <= lo) return null;
  const pos = ((la - lo) / (hi - lo)) * 100;
  return Math.min(100, Math.max(0, pos));
}

/** Arredonda o valor derivado em guaranis ao inteiro antes de formatar (§0.10). */
function roundDerived(n: number | null, quote: Currency): number | null {
  if (n === null) return null;
  return quote === "PYG" ? Math.round(n) : n;
}

function casas(n: number): string {
  return n === 1 ? "1 casa" : `${n} casas`;
}

/** Sempre 8 células, nesta ordem. `stats === null` gera células com "—". */
export function statsCells(stats: SessionStats | null, quote: Currency, now: number): StatsCell[] {
  const lastAt = stats?.last_at ?? null;
  const stale = now > 0 && lastAt !== null && now - Date.parse(lastAt) > STALE_AFTER_MS;
  const last = stats?.last ?? null;
  const lastNum = toNumber(last);
  const spreadRaw = toNumber(stats?.spread_avg ?? null);
  const pos = rangePosition(stats?.low ?? null, stats?.high ?? null, last);
  const spreadSub =
    spreadRaw !== null && lastNum !== null && lastNum > 0 ? formatPercent(spreadRaw / lastNum) : undefined;

  return [
    { id: "open", label: "Abertura", value: formatRate(stats?.open ?? null, quote) },
    { id: "high", label: "Máxima", value: formatRate(stats?.high ?? null, quote) },
    { id: "low", label: "Mínima", value: formatRate(stats?.low ?? null, quote) },
    {
      id: "last",
      label: "Último",
      value: formatRate(last, quote),
      warn: stale && lastAt !== null ? `última atualização ${formatAge(lastAt, now)}` : undefined,
    },
    {
      id: "change",
      label: "Variação",
      value: "",
      deltaAbs: toNumber(stats?.change_abs ?? null),
      deltaPct: toNumber(stats?.change_pct ?? null),
    },
    { id: "range", label: "Faixa do dia", value: pos === null ? DASH : `${Math.round(pos)}%` },
    {
      id: "quotes",
      label: "Cotações",
      value: stats ? String(stats.n_quotes) : DASH,
      sub: stats ? casas(stats.houses) : undefined,
    },
    {
      id: "spread",
      label: "Spread médio",
      value: formatRate(roundDerived(spreadRaw, quote), quote),
      sub: spreadSub,
    },
  ];
}

function stateOf(
  stats: SessionStats | null,
  loading: boolean,
  error: Error | null,
): "loading" | "error" | "empty" | "ready" {
  if (loading) return "loading";
  if (error) return "error";
  if (stats && stats.n_quotes === 0) return "empty";
  return "ready";
}

function RangeValue({ stats, quote, value }: { stats: SessionStats | null; quote: Currency; value: string }): ReactElement {
  const pos = rangePosition(stats?.low ?? null, stats?.high ?? null, stats?.last ?? null);
  const low = formatRate(stats?.low ?? null, quote);
  const high = formatRate(stats?.high ?? null, quote);
  const last = formatRate(stats?.last ?? null, quote);
  return (
    <>
      <span>{value}</span>
      <div
        role="img"
        aria-label={`Faixa do dia: mínima ${low}, máxima ${high}, último ${last}`}
        className="relative mt-2 h-2 rounded-full bg-surface-2"
      >
        {pos === null ? null : <span className="absolute top-0 h-2 w-0.5 bg-foreground" style={{ left: `${pos}%` }} />}
      </div>
      <div className="flex justify-between text-caption text-muted">
        <span>mín {low}</span>
        <span>máx {high}</span>
      </div>
    </>
  );
}

function StatTile({ cell, stats, quote }: { cell: StatsCell; stats: SessionStats | null; quote: Currency }): ReactElement {
  return (
    <div className="rounded-md border border-border bg-surface px-3 py-2">
      <dt className="text-xs text-muted">{cell.label}</dt>
      <dd className="fx-num text-heading">
        {cell.id === "change" ? (
          <span className="flex flex-wrap items-baseline gap-x-2">
            <Delta value={cell.deltaAbs ?? null} kind="abs" quote={quote} />
            <Delta value={cell.deltaPct ?? null} />
          </span>
        ) : cell.id === "range" ? (
          <RangeValue stats={stats} quote={quote} value={cell.value} />
        ) : (
          <span>{cell.value}</span>
        )}
        {cell.sub ? <span className="ml-1 text-xs text-muted">{cell.sub}</span> : null}
        {cell.warn ? (
          <span className="mt-1 flex items-center gap-1">
            <TriangleAlert size={12} aria-hidden className="text-warn" />
            <span className="text-xs text-warn">{cell.warn}</span>
          </span>
        ) : null}
      </dd>
    </div>
  );
}

/** Faixa de KPIs da sessão: abertura, máxima, mínima, último, variação, faixa, cotações e spread médio. */
export function StatsStrip({
  stats,
  quote,
  now,
  loading = false,
  error = null,
  onRetry,
  className,
}: StatsStripProps): ReactElement {
  const state = stateOf(stats, loading, error);
  const cells = statsCells(stats, quote, now);

  // Raiz `@container`: as colunas seguem a largura do bloco (no pregão ele mora na coluna do gráfico,
  // que nunca é a largura da janela). Só o estado pronto é uma `<dl>`, e ela só tem grupos dt/dd.
  const grid = "grid grid-cols-2 gap-2 @lg:grid-cols-4 @4xl:grid-cols-8";
  let body: ReactElement;
  if (state === "loading") {
    body = (
      <div className={grid}>
        <span className="sr-only">Carregando…</span>
        {Array.from({ length: TILE_COUNT }, (_, i) => (
          <Skeleton key={i} className="h-16" />
        ))}
      </div>
    );
  } else if (state === "error") {
    body = (
      <div role="alert" className="text-sm">
        Não foi possível carregar as estatísticas da sessão.{" "}
        <span className="text-muted">{error?.message}</span>
        {onRetry ? (
          <Button type="button" variant="outline" size="sm" className="ml-2" onClick={onRetry}>
            Tentar de novo
          </Button>
        ) : null}
      </div>
    );
  } else if (state === "empty") {
    body = <p className="text-sm text-muted">Sessão sem cotações até agora.</p>;
  } else {
    body = (
      <>
        <dl className={grid}>
          {cells.map((cell) => (
            <StatTile key={cell.id} cell={cell} stats={stats} quote={quote} />
          ))}
        </dl>
        <p className="mt-1 text-caption text-muted">corte diário 00:00 Assunção</p>
      </>
    );
  }

  return (
    <div
      data-testid="pregao-stats"
      data-state={state}
      aria-busy={loading || undefined}
      data-mode={stats?.data_mode === "demo" ? "demo" : undefined}
      data-day-start={stats?.day_start}
      className={cn("@container", className)}
    >
      {body}
    </div>
  );
}
