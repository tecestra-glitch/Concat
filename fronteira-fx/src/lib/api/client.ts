/**
 * API client. When NEXT_PUBLIC_API_URL is unset (or the user forces demo mode) the
 * client serves the isolated demo dataset, clearly flagged by `data_mode = "demo"`.
 */
import type { Account, Evidence, HistorySeries, JournalEntry, Opportunity, Quote, SimulationRequest, SimulationResponse, Snapshot, Source } from "./types";
import { DEMO_SERVER_TIME, allDemoQuotes, demoAccounts, demoEvidence, demoHistory, demoJournal, demoOpportunities, demoSources } from "./demo-data";

export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "").replace(/\/$/, "");

export type Mode = "demo" | "real";

export function resolveMode(preferred: Mode | "auto"): Mode {
  if (preferred === "demo") return "demo";
  if (preferred === "real") return API_URL ? "real" : "demo";
  return API_URL ? "real" : "demo";
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, { ...init, headers: { "content-type": "application/json", ...(init?.headers ?? {}) } });
  if (!res.ok) throw new ApiError(res.status, `${res.status} ${res.statusText} em ${path}`);
  return (await res.json()) as T;
}

export interface QuoteFilters {
  city?: string;
  base?: string;
  quote?: string;
  source?: string;
  modality?: string;
}

function qs(params: Record<string, string | number | undefined>): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== "" && v !== "all") p.set(k, String(v));
  const s = p.toString();
  return s ? `?${s}` : "";
}

export const api = {
  async sources(mode: Mode): Promise<Source[]> {
    return mode === "demo" ? demoSources : http<Source[]>("/v1/sources");
  },
  async quotes(mode: Mode, f: QuoteFilters = {}): Promise<Quote[]> {
    if (mode === "real") return http<Quote[]>(`/v1/quotes${qs({ ...f })}`);
    return allDemoQuotes.filter(
      (q) =>
        (!f.city || f.city === "all" || (f.city === "digital" ? q.city === null : q.city === f.city)) &&
        (!f.base || f.base === "all" || q.base === f.base) &&
        (!f.quote || f.quote === "all" || q.quote === f.quote) &&
        (!f.source || f.source === "all" || q.source_id === f.source) &&
        (!f.modality || f.modality === "all" || q.modality === f.modality),
    );
  },
  async history(mode: Mode, key: string): Promise<HistorySeries> {
    if (mode === "real") return http<HistorySeries>(`/v1/history${qs({ key, grid: 300 })}`);
    return { key, points: demoHistory(key) };
  },
  async opportunities(mode: Mode, capital?: number): Promise<Opportunity[]> {
    if (mode === "real") return http<Opportunity[]>(`/v1/opportunities${qs({ capital })}`);
    return demoOpportunities.filter((o) => !capital || o.capital_brl === String(capital));
  },
  async simulate(mode: Mode, req: SimulationRequest): Promise<SimulationResponse> {
    if (mode === "real") return http<SimulationResponse>("/v1/simulations/routes", { method: "POST", body: JSON.stringify(req) });
    const { simulateDemo } = await import("./demo-simulate");
    return simulateDemo(req);
  },
  async accounts(mode: Mode): Promise<Account[]> {
    return mode === "demo" ? demoAccounts : http<Account[]>("/v1/accounts");
  },
  async evidence(mode: Mode, source?: string): Promise<Evidence[]> {
    if (mode === "real") return http<Evidence[]>(`/v1/evidence${qs({ source })}`);
    return demoEvidence.filter((e) => !source || e.source_id === source);
  },
  async journal(mode: Mode): Promise<JournalEntry[]> {
    return mode === "demo" ? demoJournal : http<JournalEntry[]>("/v1/journal");
  },
  async snapshot(mode: Mode): Promise<Snapshot> {
    if (mode === "real") return http<Snapshot>("/v1/snapshot");
    return { cursor: "demo-0", server_time: DEMO_SERVER_TIME, quotes: allDemoQuotes, sources: demoSources, opportunities: demoOpportunities };
  },
  async health(): Promise<{ status: string; data_mode: string; version?: string } | null> {
    if (!API_URL) return null;
    try {
      return await http("/v1/health");
    } catch {
      return null;
    }
  },
  streamUrl(cursor?: string | null): string {
    return `${API_URL}/v1/stream${cursor ? `?cursor=${encodeURIComponent(cursor)}` : ""}`;
  },
};
