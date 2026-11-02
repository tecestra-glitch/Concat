"use client";
import { useQuery } from "@tanstack/react-query";
import { api, type QuoteFilters } from "./api/client";
import type { SimulationRequest } from "./api/types";
import { useSettings } from "./settings";

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
export function useOpportunities(capital?: number) {
  const { mode } = useSettings();
  return useQuery({ queryKey: ["opportunities", mode, capital], queryFn: () => api.opportunities(mode, capital), staleTime: 30_000 });
}
export function useAccounts() {
  const { mode } = useSettings();
  return useQuery({ queryKey: ["accounts", mode], queryFn: () => api.accounts(mode) });
}
export function useEvidence(source?: string) {
  const { mode } = useSettings();
  return useQuery({ queryKey: ["evidence", mode, source], queryFn: () => api.evidence(mode, source) });
}
export function useJournal() {
  const { mode } = useSettings();
  return useQuery({ queryKey: ["journal", mode], queryFn: () => api.journal(mode) });
}
export function useSimulation(req: SimulationRequest | null) {
  const { mode } = useSettings();
  return useQuery({ queryKey: ["simulation", mode, req], queryFn: () => api.simulate(mode, req!), enabled: !!req });
}
export function useBackendHealth() {
  return useQuery({ queryKey: ["health"], queryFn: () => api.health(), refetchInterval: 60_000 });
}
