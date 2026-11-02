"use client";
/**
 * TanStack Query hooks. Every key carries the resolved data mode right after the name
 * (`[name, mode, filters?]`): the live layer (`live-cache.ts`) relies on that shape to fill
 * only the active queries of the current mode, so modes never mix in the cache.
 */
import { useQuery } from "@tanstack/react-query";
import { api } from "./api/client";
import { setBackendStatus } from "./api/backend-status";
import type { CycleFilters, EvidenceFilters, OpportunityFilters, QuoteFilters, SimulationRequest } from "./api/types";
import { useSettings } from "./settings";

export type { CycleFilters, EvidenceFilters, OpportunityFilters, QuoteFilters };

export function useSources() {
  const { mode } = useSettings();
  return useQuery({ queryKey: ["sources", mode], queryFn: () => api.sources(mode), staleTime: 30_000 });
}
export function useQuotes(filters: QuoteFilters = {}) {
  const { mode } = useSettings();
  return useQuery({ queryKey: ["quotes", mode, filters], queryFn: () => api.quotes(mode, filters), staleTime: 15_000 });
}
export function useHistory(key: string | null) {
  const { mode } = useSettings();
  return useQuery({ queryKey: ["history", mode, key], queryFn: () => api.history(mode, key!), enabled: !!key, staleTime: 60_000 });
}
export function useVolatility(key: string | null, window: "1h" | "24h" = "24h") {
  const { mode } = useSettings();
  return useQuery({ queryKey: ["volatility", mode, key, window], queryFn: () => api.volatility(mode, key!, window), enabled: !!key, staleTime: 60_000 });
}
export function useBranches(sourceId: string | null) {
  const { mode } = useSettings();
  return useQuery({ queryKey: ["branches", mode, sourceId], queryFn: () => api.branches(mode, sourceId!), enabled: !!sourceId, staleTime: 300_000 });
}
/** Accepts the legacy numeric capital or the full filter object (`capital`, `channel`, `city`). */
export function useOpportunities(filters?: OpportunityFilters | number) {
  const { mode } = useSettings();
  return useQuery({ queryKey: ["opportunities", mode, filters], queryFn: () => api.opportunities(mode, filters), staleTime: 30_000 });
}
export function useCycles(filters: CycleFilters = {}) {
  const { mode } = useSettings();
  return useQuery({ queryKey: ["cycles", mode, filters], queryFn: () => api.cycles(mode, filters), staleTime: 30_000 });
}
export function useAccounts() {
  const { mode } = useSettings();
  return useQuery({ queryKey: ["accounts", mode], queryFn: () => api.accounts(mode) });
}
/** Accepts the legacy source id or the full filter object (`source`, `from`). */
export function useEvidence(filters?: EvidenceFilters | string) {
  const { mode } = useSettings();
  return useQuery({ queryKey: ["evidence", mode, filters], queryFn: () => api.evidence(mode, filters) });
}
export function useJournal() {
  const { mode } = useSettings();
  return useQuery({ queryKey: ["journal", mode], queryFn: () => api.journal(mode) });
}
export function useSimulation(req: SimulationRequest | null) {
  const { mode } = useSettings();
  return useQuery({ queryKey: ["simulation", mode, req], queryFn: () => api.simulate(mode, req!), enabled: !!req });
}
export function useMemorySummary(limit?: number) {
  const { mode } = useSettings();
  return useQuery({ queryKey: ["memory-summary", mode, limit], queryFn: () => api.memorySummary(mode, limit), staleTime: 60_000 });
}
/** Backend health for the current mode; in demo it is synthetic (`data_mode: "demo"`) and never hits the network. */
export function useBackendHealth() {
  const { mode } = useSettings();
  return useQuery({
    queryKey: ["health", mode],
    queryFn: async () => {
      const h = await api.health(mode);
      if (mode !== "demo") setBackendStatus(h ? "available" : "unavailable");
      return h;
    },
    refetchInterval: 60_000,
  });
}
