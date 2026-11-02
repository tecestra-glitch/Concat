"use client";
/** Resumo da sessão por chave (`/v1/pregao/stats`, §0.6). Sondagem de 60 s, como as cotações rápidas. */
import { keepPreviousData, queryOptions, useQuery, type UseQueryResult } from "@tanstack/react-query";
import type { ApiError, Mode } from "@/lib/api/client";
import { useSettings } from "@/lib/settings";
import { fetchStats } from "./api";
import type { SessionStats } from "./types";
import { REFETCH_FAST_MS, pregaoKeys } from "./use-candles";

export function statsQueryOptions(mode: Mode, keys: readonly string[]) {
  return queryOptions<SessionStats[], ApiError>({
    queryKey: pregaoKeys.stats(mode, keys),
    queryFn: ({ signal }) => fetchStats(mode, [...keys], { signal, now: new Date() }),
    enabled: keys.length > 0,
    staleTime: REFETCH_FAST_MS,
    refetchInterval: REFETCH_FAST_MS,
    refetchOnWindowFocus: false,
    placeholderData: keepPreviousData,
  });
}

/** Indexa o resumo pela chave da série. */
export function statsByKey(stats: readonly SessionStats[] | undefined): ReadonlyMap<string, SessionStats> {
  return new Map<string, SessionStats>(stats?.map((s): [string, SessionStats] => [s.key, s]) ?? []);
}

export function useSessionStats(keys: readonly string[]): UseQueryResult<SessionStats[], ApiError> {
  const { mode } = useSettings();
  return useQuery(statsQueryOptions(mode, keys));
}
