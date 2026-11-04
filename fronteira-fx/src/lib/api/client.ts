/**
 * API client (D3 / D5). Every call takes the resolved mode:
 * - `real` and `simulation` go to the backend through the Next proxy (`/api/fx`, which injects the
 *   API key server-side). Each backend instance serves ONE data mode, so every call declares the mode it
 *   expects (`?data_mode=`): an instance in another mode answers `409` and nothing is read or written, and a
 *   response stamped with another `data_mode` is rejected here as well (SEC-01: the modes never mix).
 * - `demo` serves the isolated demo dataset (flagged `data_mode = "demo"`) and never touches the network.
 *
 * `NEXT_PUBLIC_API_URL` is honoured only for local development against a backend without key
 * (it bypasses the proxy); production leaves it unset.
 */
import type {
  Account,
  AccountInput,
  AccountPatch,
  BackendHealth,
  Branch,
  Cycle,
  CycleFilters,
  Evidence,
  EvidenceFilters,
  HistorySeries,
  JournalEntry,
  JournalInput,
  KnowledgeHit,
  KnowledgeQuery,
  Memory,
  MemoryQuery,
  MemorySummary,
  Mode,
  Opportunity,
  OpportunityFilters,
  Quote,
  QuoteFilters,
  QuoteRequest,
  QuoteRequestResponse,
  SimulationRequest,
  SimulationResponse,
  Snapshot,
  Source,
  Volatility,
} from "./types";
import type { AlertRule, AlertRuleInput } from "./watch";
import { InstitutionSchema, type Institution } from "./institutions";
import type { BackendStatus } from "./backend-status";
import { DEMO_SERVER_TIME, allDemoQuotes, demoAccounts, demoBranches, demoEvidence, demoHistory, demoJournal, demoOpportunities, demoSources } from "./demo-data";
import { demoEdges, demoParkedBalances } from "./demo-graph";
import { demoDeleteRule, demoUpdateRule } from "./demo-watch";
import { dec, findCycles } from "../graph";
import { toNumber } from "../format";
import { computeVolatility } from "../volatility";

export type { Mode, QuoteFilters } from "./types";
export type { BackendStatus } from "./backend-status";

/** Dev-only override (no key). Empty in production: the browser only ever talks to the proxy. */
export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "").replace(/\/$/, "");
/** Base of every request the browser makes. */
export const API_BASE = API_URL || "/api/fx";

/**
 * D3: an explicit preference always wins; `auto` follows the mode the backend instance declares in
 * `/v1/health` once it answered (`real` when it did not say), otherwise `demo` (never a silent mix).
 */
export function resolveMode(preferred: Mode | "auto", backend: BackendStatus, backendMode?: Mode | null): Mode {
  if (preferred !== "auto") return preferred;
  if (backend !== "available") return "demo";
  return backendMode ?? "real";
}

/**
 * SEC-01: the preference asks for a backend mode the instance does not serve. The backend refuses those
 * calls (409); the UI says so instead of labelling foreign data. The demo dataset is local and never conflicts.
 */
export function modeConflict(mode: Mode, backendMode: Mode | null | undefined): boolean {
  return mode !== "demo" && !!backendMode && backendMode !== mode;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function errorDetail(res: Response): Promise<string> {
  const text = await res.text().catch(() => "");
  if (text) {
    try {
      const body = JSON.parse(text) as { detail?: unknown; message?: unknown };
      const d = body.detail ?? body.message;
      if (typeof d === "string" && d) return d;
      if (Array.isArray(d)) return d.map((x: unknown) => (x && typeof x === "object" && "msg" in x ? String((x as { msg: unknown }).msg) : JSON.stringify(x))).join("; ");
    } catch {
      /* not JSON: fall through to the status text */
    }
  }
  return res.statusText || "erro";
}

/** The `data_mode` a request declared in its query string, if any. */
function declaredMode(path: string): string | null {
  const q = path.indexOf("?");
  return q === -1 ? null : new URLSearchParams(path.slice(q + 1)).get("data_mode");
}

/**
 * SEC-01, second line of defence: a record (or a list of records) stamped with another `data_mode` than the
 * request declared never reaches the UI. Nested objects are not inspected: a real instance legitimately tags
 * the opportunities of a simulation with `simulation` inside the simulation response (D3).
 */
function assertSameMode(path: string, expected: string, body: unknown): void {
  for (const item of Array.isArray(body) ? body : [body]) {
    if (item === null || typeof item !== "object") continue;
    const stamp = (item as { data_mode?: unknown }).data_mode;
    if (typeof stamp === "string" && stamp !== expected) {
      throw new ApiError(409, `409 resposta em data_mode=${stamp} para um pedido em data_mode=${expected} em ${path}; os modos nunca se misturam`);
    }
  }
}

/**
 * The single HTTP helper (watch.ts shares it). `Content-Type` only when there is a body,
 * `204`/empty body → `undefined`, non-2xx → `ApiError` carrying the backend `detail`.
 */
export async function http<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body !== undefined && init.body !== null && !headers.has("content-type")) headers.set("content-type", "application/json");
  const res = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (!res.ok) throw new ApiError(res.status, `${res.status} ${await errorDetail(res)} em ${path}`);
  if (res.status === 204 || res.status === 205) return undefined as T;
  const text = await res.text();
  if (text === "") return undefined as T;
  const body = JSON.parse(text) as unknown;
  const expected = declaredMode(path);
  if (expected) assertSameMode(path, expected, body);
  return body as T;
}

export type QueryParams = Record<string, string | number | boolean | null | undefined>;

/** Query string builder: skips `undefined`, `null`, `""` and the UI's `"all"` sentinel. */
export function qs(params: QueryParams): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "" || v === "all") continue;
    p.set(k, String(v));
  }
  const s = p.toString();
  return s ? `?${s}` : "";
}

/** SEC-01: the mode every backend call expects; the instance answers 409 when it serves another one. */
export function modeQuery(mode: Mode): { data_mode?: Exclude<Mode, "demo"> } {
  return mode === "demo" ? {} : { data_mode: mode };
}

/** GET /v1/rag/search?q=&k=&tag= (path only; tests and the client share it). */
export function knowledgeSearchPath(mode: Mode, f: KnowledgeQuery): string {
  return `/v1/rag/search${qs({ q: f.q, k: f.k, tag: f.tag, ...modeQuery(mode) })}`;
}

/** GET /v1/memory?q=&kind=&tag=&limit= (the UI's "all" sentinel is dropped by `qs`). */
export function memoryListPath(mode: Mode, f: MemoryQuery): string {
  return `/v1/memory${qs({ q: f.q, kind: f.kind, tag: f.tag, limit: f.limit, ...modeQuery(mode) })}`;
}

const active = (v: string | number | null | undefined): v is string | number => v !== undefined && v !== null && v !== "" && v !== "all";

// ---------------------------------------------------------------------------------------------
// Demo-side mutable stores (accounts, journal) so create/update round-trip inside the session.
// ---------------------------------------------------------------------------------------------

let demoAccountStore: Account[] | null = null;
let demoJournalStore: JournalEntry[] | null = null;
let localCounter = 0;

const localId = (): string => `local-${++localCounter}`;
const nowIso = (): string => new Date().toISOString();

function demoAccountList(): Account[] {
  if (!demoAccountStore) demoAccountStore = demoAccounts.map((a) => ({ ...a }));
  return demoAccountStore;
}

function demoJournalList(): JournalEntry[] {
  if (!demoJournalStore) demoJournalStore = demoJournal.map((j) => ({ ...j }));
  return demoJournalStore;
}

/** Test helper: forgets demo accounts/journal created in this session. */
export function resetDemoClient(): void {
  demoAccountStore = null;
  demoJournalStore = null;
  localCounter = 0;
}

function demoVolatility(key: string, window: Volatility["window"]): Volatility {
  const windowMs = window === "1h" ? 3_600_000 : 86_400_000;
  const obs = demoHistory(key).points.flatMap((p) => {
    const t = Date.parse(p.t);
    const value = toNumber(p.mid);
    return Number.isFinite(t) && value !== null ? [{ t, value }] : [];
  });
  const now = obs.length ? Math.max(...obs.map((o) => o.t)) : Date.now();
  const r = computeVolatility(obs, windowMs, now);
  return {
    key,
    window,
    grid_s: 300,
    returns_used: r.returnsUsed,
    min_returns: r.minReturns,
    stdev_pct_per_5m: r.stdevPctPer5m === null ? null : dec(r.stdevPctPer5m, 6),
    coverage_pct: dec(r.coveragePct, 2),
    gaps: r.gaps,
    status: r.status,
  };
}

// ---------------------------------------------------------------------------------------------
// Client
// ---------------------------------------------------------------------------------------------

export const api = {
  async sources(mode: Mode): Promise<Source[]> {
    if (mode !== "demo") return http<Source[]>(`/v1/sources${qs(modeQuery(mode))}`);
    return demoSources;
  },
  /** `city = "digital"` is not a backend value: it is dropped from the query and applied as `city === null`. */
  async quotes(mode: Mode, f: QuoteFilters = {}): Promise<Quote[]> {
    const digital = f.city === "digital";
    if (mode !== "demo") {
      const list = await http<Quote[]>(`/v1/quotes${qs({ city: digital ? undefined : f.city, base: f.base, quote: f.quote, source: f.source, modality: f.modality, amount: f.amount, ...modeQuery(mode) })}`);
      return digital ? list.filter((q) => q.city === null) : list;
    }
    const amount = active(f.amount) ? toNumber(f.amount) : null;
    return allDemoQuotes.filter(
      (q) =>
        (!active(f.city) || (digital ? q.city === null : q.city === f.city)) &&
        (!active(f.base) || q.base === f.base) &&
        (!active(f.quote) || q.quote === f.quote) &&
        (!active(f.source) || q.source_id === f.source) &&
        (!active(f.modality) || q.modality === f.modality) &&
        // like the backend (`latest_quotes`): a quote without amount is generic and stays (MED-06)
        (amount === null || q.amount_base === null || toNumber(q.amount_base) === amount),
    );
  },
  /** `key` is the D2 series_key. */
  async history(mode: Mode, key: string): Promise<HistorySeries> {
    if (mode !== "demo") return http<HistorySeries>(`/v1/history${qs({ key, grid: 300, ...modeQuery(mode) })}`);
    return demoHistory(key);
  },
  async volatility(mode: Mode, key: string, window: Volatility["window"] = "24h"): Promise<Volatility> {
    if (mode !== "demo") return http<Volatility>(`/v1/volatility${qs({ key, window, ...modeQuery(mode) })}`);
    return demoVolatility(key, window);
  },
  async branches(mode: Mode, sourceId: string): Promise<Branch[]> {
    if (mode !== "demo") return http<Branch[]>(`/v1/sources/${encodeURIComponent(sourceId)}/branches${qs(modeQuery(mode))}`);
    return demoBranches.filter((b) => b.source_id === sourceId);
  },
  /** POST /v1/quotes/request: on-demand quote (e.g. a remittance simulation for a given amount). */
  async requestQuote(mode: Mode, req: QuoteRequest): Promise<QuoteRequestResponse> {
    if (mode !== "demo") return http<QuoteRequestResponse>(`/v1/quotes/request${qs(modeQuery(mode))}`, { method: "POST", body: JSON.stringify(req) });
    const source = demoSources.find((s) => s.id === req.source_id);
    if (!source) throw new ApiError(404, `fonte ${req.source_id} não encontrada (demo)`);
    if (source.health === "blocked") return { status: "blocked", reason: source.last_error ?? "fonte bloqueada (demonstração)" };
    const amount = req.params.amount;
    const ofSource = allDemoQuotes.filter((q) => q.source_id === req.source_id);
    const quote = (amount !== undefined && amount !== null ? ofSource.find((q) => toNumber(q.amount_base) === toNumber(amount)) : undefined) ?? ofSource[0] ?? null;
    return { status: "done", quote };
  },
  /**
   * Accepts the capital alone (number) or the full filter set; all three filters are really sent, except
   * `city = "digital"`, which is not a backend value (422): it is applied here as `city === null` (MED-05).
   */
  async opportunities(mode: Mode, filters?: OpportunityFilters | number): Promise<Opportunity[]> {
    const f: OpportunityFilters = typeof filters === "number" ? { capital: filters } : (filters ?? {});
    if (mode !== "demo") {
      const digital = f.city === "digital";
      const list = await http<Opportunity[]>(`/v1/opportunities${qs({ capital: f.capital, channel: f.channel, city: digital ? undefined : f.city, ...modeQuery(mode) })}`);
      return digital ? list.filter((o) => o.city === null) : list;
    }
    const capital = active(f.capital) ? toNumber(f.capital) : null;
    return demoOpportunities.filter(
      (o) =>
        (capital === null || !(capital > 0) || toNumber(o.capital_brl) === capital) &&
        (!active(f.channel) || o.channel === f.channel) &&
        (!active(f.city) || (f.city === "digital" ? o.city === null : o.city === f.city)),
    );
  },
  /** D1: GET /v1/opportunities/cycles. Demo mode runs the TS mirror of the engine on the demo graph. */
  async cycles(mode: Mode, f: CycleFilters = {}): Promise<Cycle[]> {
    if (mode !== "demo") return http<Cycle[]>(`/v1/opportunities/cycles${qs({ max_len: f.maxLen ?? 4, min_roi: f.minRoi, start: f.start, limit: f.limit, ...modeQuery(mode) })}`);
    const all = findCycles(demoEdges(), demoParkedBalances(), { maxLen: f.maxLen ?? 4, minRoi: f.minRoi, dataMode: "demo" });
    return (f.start ? all.filter((c) => c.start === f.start) : all).slice(0, f.limit ?? 200);
  },
  async simulate(mode: Mode, req: SimulationRequest): Promise<SimulationResponse> {
    if (mode !== "demo") return http<SimulationResponse>(`/v1/simulations/routes${qs(modeQuery(mode))}`, { method: "POST", body: JSON.stringify(req) });
    const { simulateDemo } = await import("./demo-simulate");
    return simulateDemo(req);
  },
  /** Cadastro de instituições (`GET /v1/institutions`), validado na borda. Demonstração não toca a rede: sem cadastro. */
  async institutions(mode: Mode): Promise<Institution[]> {
    if (mode === "demo") return [];
    return InstitutionSchema.array().parse(await http<unknown>("/v1/institutions"));
  },
  async accounts(mode: Mode): Promise<Account[]> {
    if (mode !== "demo") return http<Account[]>(`/v1/accounts${qs(modeQuery(mode))}`);
    return demoAccountList().map((a) => ({ ...a }));
  },
  async createAccount(mode: Mode, input: AccountInput): Promise<Account> {
    if (mode !== "demo") return http<Account>(`/v1/accounts${qs(modeQuery(mode))}`, { method: "POST", body: JSON.stringify(input) });
    const acc: Account = { ...input, id: localId(), updated_at: nowIso() };
    demoAccountList().push(acc);
    return { ...acc };
  },
  async updateAccount(mode: Mode, id: string, patch: AccountPatch): Promise<Account> {
    if (mode !== "demo") return http<Account>(`/v1/accounts/${encodeURIComponent(id)}${qs(modeQuery(mode))}`, { method: "PATCH", body: JSON.stringify(patch) });
    const list = demoAccountList();
    const idx = list.findIndex((a) => a.id === id);
    if (idx === -1) throw new ApiError(404, `conta ${id} não encontrada (demonstração)`);
    list[idx] = { ...list[idx], ...patch, id, updated_at: nowIso() };
    return { ...list[idx] };
  },
  /** Accepts the source id alone (string) or `{ source, from }`. */
  async evidence(mode: Mode, filters?: EvidenceFilters | string): Promise<Evidence[]> {
    const f: EvidenceFilters = typeof filters === "string" ? { source: filters } : (filters ?? {});
    if (mode !== "demo") return http<Evidence[]>(`/v1/evidence${qs({ source: f.source, from: f.from, ...modeQuery(mode) })}`);
    const from = f.from ? Date.parse(f.from) : NaN;
    return demoEvidence.filter((e) => (!active(f.source) || e.source_id === f.source) && (Number.isNaN(from) || Date.parse(e.captured_at) >= from));
  },
  async evidenceById(mode: Mode, id: string): Promise<Evidence> {
    if (mode !== "demo") return http<Evidence>(`/v1/evidence/${encodeURIComponent(id)}${qs(modeQuery(mode))}`);
    const ev = demoEvidence.find((e) => e.id === id);
    if (!ev) throw new ApiError(404, `evidência ${id} não encontrada (demonstração)`);
    return ev;
  },
  async journal(mode: Mode): Promise<JournalEntry[]> {
    if (mode !== "demo") return http<JournalEntry[]>(`/v1/journal${qs(modeQuery(mode))}`);
    return demoJournalList().map((j) => ({ ...j }));
  },
  async createJournal(mode: Mode, input: JournalInput): Promise<JournalEntry> {
    if (mode !== "demo") return http<JournalEntry>(`/v1/journal${qs(modeQuery(mode))}`, { method: "POST", body: JSON.stringify(input) });
    const entry: JournalEntry = { ...input, id: localId(), ts: nowIso() };
    demoJournalList().unshift(entry);
    return { ...entry };
  },
  /** PATCH /v1/alerts/rules/{id} (the rule list itself lives in watch.ts → watchApi.rules). */
  async updateRule(mode: Mode, id: string, patch: Partial<AlertRuleInput>): Promise<AlertRule> {
    if (mode !== "demo") return http<AlertRule>(`/v1/alerts/rules/${encodeURIComponent(id)}${qs(modeQuery(mode))}`, { method: "PATCH", body: JSON.stringify(patch) });
    try {
      return demoUpdateRule(id, patch);
    } catch (e) {
      throw new ApiError(404, e instanceof Error ? e.message : `regra ${id} não encontrada (demonstração)`);
    }
  },
  async deleteRule(mode: Mode, id: string): Promise<void> {
    if (mode !== "demo") {
      await http<void>(`/v1/alerts/rules/${encodeURIComponent(id)}${qs(modeQuery(mode))}`, { method: "DELETE" });
      return;
    }
    demoDeleteRule(id);
  },
  /** RAG over documentation/fees/hours. Demo has no corpus: an empty list, never the network. */
  async searchKnowledge(mode: Mode, f: KnowledgeQuery): Promise<KnowledgeHit[]> {
    if (mode === "demo") return [];
    return http<KnowledgeHit[]>(knowledgeSearchPath(mode, f));
  },
  /** GET /v1/memory. Demo has no memory: an empty list, never the network. */
  async memory(mode: Mode, f: MemoryQuery): Promise<Memory[]> {
    if (mode === "demo") return [];
    return http<Memory[]>(memoryListPath(mode, f));
  },
  /** GET /v1/memory/summary?limit= → { summary } (text for the overview). */
  async memorySummary(mode: Mode, limit?: number): Promise<MemorySummary> {
    if (mode !== "demo") return http<MemorySummary>(`/v1/memory/summary${qs({ limit, ...modeQuery(mode) })}`);
    return { summary: "Demonstração — memória ilustrativa: nenhuma operação real registrada. Os dados desta tela não vêm do backend." };
  },
  async snapshot(mode: Mode): Promise<Snapshot> {
    if (mode !== "demo") return http<Snapshot>(`/v1/snapshot${qs(modeQuery(mode))}`);
    return { cursor: "demo-0", server_time: DEMO_SERVER_TIME, quotes: allDemoQuotes, sources: demoSources, opportunities: demoOpportunities, data_mode: "demo" };
  },
  /**
   * `null` when the backend (or the proxy) is unreachable; demo answers locally. Never declares a mode:
   * health is how the client learns which mode the instance serves (SEC-01).
   */
  async health(mode: Mode = "real"): Promise<BackendHealth | null> {
    if (mode === "demo") return { status: "ok", data_mode: "demo", server_time: DEMO_SERVER_TIME };
    try {
      return await http<BackendHealth>("/v1/health");
    } catch {
      return null;
    }
  },
  /** SSE endpoint (through the proxy); `cursor` resumes after the last event id, absent after a 410. */
  streamUrl(mode: Mode, cursor?: string | null): string {
    return `${API_BASE}/v1/stream${qs({ cursor: cursor ?? undefined, ...modeQuery(mode) })}`;
  },
};
