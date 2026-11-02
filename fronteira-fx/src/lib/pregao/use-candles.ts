"use client";
/**
 * Hooks de velas do pregão (§8). Modo `demo` vem dos geradores da fundação, sem rede (§0.6).
 * Piso de sondagem de 60 s: nenhum intervalo ou staleTime abaixo disso.
 */
import { keepPreviousData, queryOptions, useQueries, useQuery, type UseQueryResult } from "@tanstack/react-query";
import type { ApiError, Mode } from "@/lib/api/client";
import { useSettings } from "@/lib/settings";
import { fetchCandles } from "./api";
import type { CandleSeries, Timeframe } from "./types";

export const REFETCH_FAST_MS = 60_000;
export const REFETCH_SLOW_MS = 300_000;

export const pregaoKeys = {
  candles: (mode: Mode, key: string, tf: Timeframe, limit: number) => ["pregao", "candles", mode, key, tf, limit] as const,
  stats: (mode: Mode, keys: readonly string[]) => ["pregao", "stats", mode, keys.join(",")] as const,
  sessions: (mode: Mode) => ["pregao", "sessions", mode] as const,
};

/** "15m" sonda a cada 60 s; "1h", "4h" e "1d" a cada 300 s. */
export function refetchMsFor(tf: Timeframe): number {
  return tf === "15m" ? REFETCH_FAST_MS : REFETCH_SLOW_MS;
}

export function candlesQueryOptions(mode: Mode, key: string | null, tf: Timeframe, limit = 300) {
  const interval = refetchMsFor(tf);
  return queryOptions<CandleSeries, ApiError>({
    queryKey: pregaoKeys.candles(mode, key ?? "", tf, limit),
    queryFn: ({ signal }) => fetchCandles(mode, key ?? "", tf, { limit, signal, now: new Date() }),
    enabled: key !== null && key.length > 0,
    staleTime: interval,
    refetchInterval: interval,
    refetchOnWindowFocus: false,
    placeholderData: keepPreviousData,
  });
}

export function useCandles(key: string | null, tf: Timeframe, opts: { limit?: number } = {}): UseQueryResult<CandleSeries, ApiError> {
  const { mode } = useSettings();
  return useQuery(candlesQueryOptions(mode, key, tf, opts.limit));
}

/** Fechamentos de 1 h por chave, para as miniaturas da lista. Vazio (`[]`) enquanto carrega. */
export function useSparklines(keys: readonly string[], count = 24): Record<string, number[]> {
  const { mode } = useSettings();
  return useQueries({
    queries: keys.map((k) => candlesQueryOptions(mode, k, "1h", count)),
    combine: (results) => Object.fromEntries(results.map((r, i) => [keys[i], (r.data?.candles ?? []).map((c) => Number(c.c))])),
  });
}
