"use client";
/** Sessões das casas (`/v1/pregao/sessions`, §0.6), incluindo a referência BCP com `reference: true`. */
import { queryOptions, useQuery, type UseQueryResult } from "@tanstack/react-query";
import type { ApiError, Mode } from "@/lib/api/client";
import { useSettings } from "@/lib/settings";
import { fetchSessions } from "./api";
import type { HouseSession } from "./types";
import { REFETCH_FAST_MS, pregaoKeys } from "./use-candles";

export function sessionsQueryOptions(mode: Mode) {
  return queryOptions<HouseSession[], ApiError>({
    queryKey: pregaoKeys.sessions(mode),
    queryFn: ({ signal }) => fetchSessions(mode, { signal, now: new Date() }),
    staleTime: REFETCH_FAST_MS,
    refetchInterval: REFETCH_FAST_MS,
    refetchOnWindowFocus: false,
  });
}

export function useHouseSessions(): UseQueryResult<HouseSession[], ApiError> {
  const { mode } = useSettings();
  return useQuery(sessionsQueryOptions(mode));
}
