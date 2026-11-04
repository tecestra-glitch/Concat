"use client";
/**
 * TanStack Query hooks. Every key carries the resolved data mode right after the name
 * (`[name, mode, filters?]`): the live layer (`live-cache.ts`) relies on that shape to fill
 * only the active queries of the current mode, so modes never mix in the cache.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./api/client";
import { setBackendStatus } from "./api/backend-status";
import type { CycleFilters, EvidenceFilters, OpportunityFilters, Plan, PlanCreate, QuoteFilters, SimulationRequest, StepDone } from "./api/types";
import type { NewsFilters } from "./api/market";
import type { Instrument, Interval } from "./api/triangulador";
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
/** Cadastro de instituições: muda raramente (arquivo versionado), então o cache é longo. */
export function useInstitutions() {
  const { mode } = useSettings();
  return useQuery({ queryKey: ["institutions", mode], queryFn: () => api.institutions(mode), staleTime: 60 * 60_000 });
}
/** Planos deste modo, do mais recente. Só leitura da lista; decisões e passos vão pelas mutações abaixo. */
export function usePlans() {
  const { mode } = useSettings();
  return useQuery({ queryKey: ["plans", mode], queryFn: () => api.plans(mode), staleTime: 5_000 });
}
export function usePlan(id: string) {
  const { mode } = useSettings();
  return useQuery({ queryKey: ["plan", mode, id], queryFn: () => api.plan(mode, id), enabled: !!id, staleTime: 5_000 });
}
/** Gera o plano a partir de um ciclo atual. Não executa nada: só cria a proposta. */
export function useCreatePlan() {
  const { mode } = useSettings();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: PlanCreate) => api.createPlan(mode, body),
    onSuccess: (plan) => {
      qc.setQueryData(["plan", mode, plan.id], plan);
      void qc.invalidateQueries({ queryKey: ["plans", mode] });
    },
  });
}
/** Aprovar, recusar e marcar passo: cada uma devolve o plano atualizado, que vai direto para o cache. */
export function usePlanDecision(id: string) {
  const { mode } = useSettings();
  const qc = useQueryClient();
  const store = (plan: Plan) => {
    qc.setQueryData(["plan", mode, id], plan);
    void qc.invalidateQueries({ queryKey: ["plans", mode] });
  };
  return {
    approve: useMutation({ mutationFn: () => api.approvePlan(mode, id), onSuccess: store }),
    reject: useMutation({ mutationFn: () => api.rejectPlan(mode, id), onSuccess: store }),
    completeStep: useMutation({ mutationFn: ({ n, body }: { n: number; body: StepDone }) => api.completePlanStep(mode, id, n, body), onSuccess: (plan) => { store(plan); void qc.invalidateQueries({ queryKey: ["journal", mode] }); } }),
  };
}
export function useAccounts() {
  const { mode } = useSettings();
  return useQuery({ queryKey: ["accounts", mode], queryFn: () => api.accounts(mode) });
}
/** Conexões do modo e se o agregador de Open Finance está configurado (`["connections", mode]`). */
export function useConnections() {
  const { mode } = useSettings();
  return useQuery({ queryKey: ["connections", mode], queryFn: () => api.connections(mode) });
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
/**
 * Módulo market (Economia e cripto). Chave `["market", mode, …]`: o stream invalida `["market", mode]` quando chega
 * manchete nova ou alerta de volatilidade; o intervalo de 60 s é só a rede de segurança (o backend sonda no piso de 60 s).
 */
export function useMarketNews(f: NewsFilters = {}) {
  const { mode } = useSettings();
  return useQuery({ queryKey: ["market", mode, "news", f], queryFn: () => api.marketNews(mode, f), refetchInterval: 60_000, staleTime: 30_000 });
}
export function useMarketQuotes() {
  const { mode } = useSettings();
  return useQuery({ queryKey: ["market", mode, "quotes"], queryFn: () => api.marketQuotes(mode), refetchInterval: 60_000, staleTime: 30_000 });
}
export function useMarketVolatility() {
  const { mode } = useSettings();
  return useQuery({ queryKey: ["market", mode, "volatility"], queryFn: () => api.marketVolatility(mode), refetchInterval: 60_000, staleTime: 30_000 });
}

/** Telas do triangulador (U09). Leitura de `/v1/market/*`, atualizada a cada 60 s (o backend cacheia no mesmo TTL). */
export function useTriangles(f: { minRoi?: string; start?: string; limit?: number; route?: "celular" | "todos" } = {}) {
  const { mode } = useSettings();
  return useQuery({ queryKey: ["tri", mode, "triangles", f], queryFn: () => api.triangles(mode, f), refetchInterval: 60_000, staleTime: 30_000 });
}
export function useCryptoRefs() {
  const { mode } = useSettings();
  return useQuery({ queryKey: ["tri", mode, "crypto"], queryFn: () => api.cryptoRefs(mode), refetchInterval: 60_000, staleTime: 30_000 });
}
export function useFxRefs() {
  const { mode } = useSettings();
  return useQuery({ queryKey: ["tri", mode, "fx"], queryFn: () => api.fxRefs(mode), refetchInterval: 60_000, staleTime: 30_000 });
}
export function useMacroRefs() {
  const { mode } = useSettings();
  return useQuery({ queryKey: ["tri", mode, "macro"], queryFn: () => api.macroRefs(mode), refetchInterval: 60_000, staleTime: 30_000 });
}
export function useIndicators(instrument: Instrument, interval: Interval) {
  const { mode } = useSettings();
  return useQuery({ queryKey: ["tri", mode, "indicators", instrument, interval], queryFn: () => api.indicators(mode, instrument, interval), refetchInterval: 60_000, staleTime: 30_000 });
}
export function useSentiment(limit = 30) {
  const { mode } = useSettings();
  return useQuery({ queryKey: ["tri", mode, "sentiment", limit], queryFn: () => api.sentiment(mode, limit), refetchInterval: 60_000, staleTime: 30_000 });
}

/** Backend health for the current mode; in demo it is synthetic (`data_mode: "demo"`) and never hits the network. */
export function useBackendHealth() {
  const { mode } = useSettings();
  return useQuery({
    queryKey: ["health", mode],
    queryFn: async () => {
      const h = await api.health(mode);
      if (mode !== "demo") setBackendStatus(h ? "available" : "unavailable", h?.data_mode);
      return h;
    },
    refetchInterval: 60_000,
  });
}
