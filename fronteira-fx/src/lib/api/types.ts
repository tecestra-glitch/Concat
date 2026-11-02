/** Mirrors docs/api-contract.md. Money travels as decimal strings. */
export type Currency = "BRL" | "USD" | "PYG";
export type City = "CDE" | "ASU" | "PJC" | null;
/** `aggregator` = agregador de terceiros (dolarPy): referência, nunca executável. */
export type Channel = "digital" | "physical" | "aggregator";
/** `reference` = cotação de referência (BCP, dolarPy): só comparação, nunca aresta nem ranking. */
export type Modality = "cash" | "transfer" | "account" | "card_debit" | "card_credit" | "card_virtual" | "reference";
export type QuoteKind = "market_reference" | "indicative" | "executable";
export type SourceMethod = "official_api" | "html" | "browser" | "manual";
export type Health = "ok" | "degraded" | "blocked" | "stale" | "unknown";
export type Confidence = "quoted" | "estimated" | "incomplete";
export type DataMode = "real" | "simulation" | "demo";
/** D3/SEC-01: the three data modes never mix; each backend instance serves one, and every call declares it (`?data_mode=`). */
export type Mode = DataMode;
export type OpportunityKind = "cycle" | "remittance_saving" | "purchase_saving";

/** GET /v1/health */
export interface BackendHealth {
  status: string;
  data_mode: DataMode;
  db?: string;
  version?: string;
  server_time?: string;
}

/** Fixed (`amount`) and/or percentage over the input (`pct`); unknown parts are null. */
export interface Fee {
  label: string;
  amount: string | null;
  currency: Currency;
  pct?: string | null;
}

export interface Source {
  id: string;
  name: string;
  kind: "exchange_house" | "remittance" | "bank" | "fintech" | "central_bank";
  method: SourceMethod;
  url: string;
  health: Health;
  last_success_at: string | null;
  last_error: string | null;
  capabilities: string[];
  limitations: string[];
  coverage: { cities: Exclude<City, null>[]; currencies: Currency[] };
  poll_interval_s: number;
  data_mode: DataMode;
}

export interface Branch {
  id: string;
  source_id: string;
  name: string;
  city: Exclude<City, null>;
  address: string | null;
}

export interface Quote {
  id: string;
  /** D2: `source:city|digital:BASE/QUOTE:modality[:@branch][:amount][:ctx8]` — addresses history, volatility and SSE updates. */
  series_key: string;
  source_id: string;
  branch_id: string | null;
  city: City;
  base: Currency;
  quote: Currency;
  buy: string | null;
  sell: string | null;
  unit_note: string;
  amount_base: string | null;
  modality: Modality;
  kind: QuoteKind;
  channel: Channel;
  context: Record<string, string | null> | null;
  fees: Fee[];
  captured_at: string;
  declared_updated_at: string | null;
  valid_until: string | null;
  evidence_id: string | null;
  data_mode: DataMode;
}

/** GET /v1/quotes filters (backend accepts city, base, quote, source, modality, amount). */
export interface QuoteFilters {
  city?: string;
  base?: string;
  quote?: string;
  source?: string;
  modality?: string;
  amount?: string | number;
}

/** POST /v1/quotes/request */
export interface QuoteRequest {
  source_id: string;
  params: Record<string, string | number | null>;
}

export interface QuoteRequestResponse {
  status: "done" | "queued" | "blocked";
  quote?: Quote | null;
  job_id?: string;
  reason?: string;
}

export interface HistoryPoint {
  t: string;
  buy: string | null;
  sell: string | null;
  mid: string | null;
}

export interface HistorySeries {
  key: string;
  points: HistoryPoint[];
}

export interface Volatility {
  key: string;
  window: "1h" | "24h";
  grid_s: number;
  returns_used: number;
  min_returns: number;
  stdev_pct_per_5m: string | null;
  coverage_pct: string;
  gaps: number;
  status: "ok" | "insufficient_data" | "stale_input";
}

export interface Account {
  id: string;
  institution: string;
  label: string;
  currency: Currency;
  kind: "bank" | "fintech" | "cash" | "card_debit" | "card_credit" | "card_virtual";
  location: "ASU" | "CDE" | "PJC" | "digital";
  balance_free: string;
  balance_reserved: string;
  balance_in_transit: string;
  updated_at: string;
}

/** POST /v1/accounts */
export type AccountInput = Omit<Account, "id" | "updated_at">;
/** PATCH /v1/accounts/{id} */
export type AccountPatch = Partial<Pick<Account, "label" | "balance_free" | "balance_reserved" | "balance_in_transit">>;

export interface Position {
  currency: Currency;
  account_id: string | null;
  location: string;
  modality: Modality;
  amount: string;
}

export interface RouteStep {
  n: number;
  description: string;
  from: Position;
  to: Position;
  rate: string | null;
  rate_note: string;
  amount_in: string;
  amount_out: string;
  fees: Fee[];
  duration: string;
  promo: string | null;
  confidence: Confidence;
  evidence_id: string | null;
}

export interface Opportunity {
  id: string;
  title: string;
  kind: OpportunityKind;
  channel: Channel;
  city: City;
  capital_brl: string;
  final_value_brl: string;
  net_gain_brl: string;
  roi: string;
  effective_rate: string;
  valuation_currency: Currency;
  steps: RouteStep[];
  confidence: Confidence;
  pending_costs: string[];
  in_main_ranking: boolean;
  ranking_reason: string;
  comparable_best_digital_roi: string | null;
  computed_at: string;
  data_mode: DataMode;
}

/** GET /v1/opportunities filters. */
export interface OpportunityFilters {
  capital?: string | number;
  channel?: Channel | "all" | string;
  city?: string;
}

/** D1: edge of the positions graph. Money fields are decimal strings. */
export type EdgeKind = "quote" | "transfer" | "deposit" | "withdraw";

export interface Edge {
  from: string; // `${currency}@${venue}`
  to: string;
  kind: EdgeKind;
  rate: string; // units of `to` per 1 unit of `from`, before costs
  fee_pct: string; // proportional cost on the input (0.01 = 1 %)
  fee_fixed: string; // fixed cost in the OUTPUT currency
  minutes: number;
  via: string;
  confidence: Confidence;
  evidence_id: string | null;
}

/** D1: GET /v1/opportunities/cycles item. */
export interface Cycle {
  start: string;
  path: string[];
  edges: Edge[];
  amount_in: string;
  amount_out: string;
  gain: string;
  roi: string;
  minutes: number;
  confidence: Confidence;
  data_mode: DataMode;
}

/** GET /v1/opportunities/cycles?max_len=&min_roi=&start=&limit= */
export interface CycleFilters {
  maxLen?: number; // 2..6, default 4
  minRoi?: string; // decimal string
  start?: string; // node key `${currency}@${venue}`
  limit?: number; // 1..500, default 200
}

export interface Evidence {
  id: string;
  source_id: string;
  kind: "html" | "screenshot" | "json" | "manual";
  url: string;
  captured_at: string;
  sha256: string;
  excerpt: string;
  rules: string[];
}

/** GET /v1/evidence?source=&from= */
export interface EvidenceFilters {
  source?: string;
  from?: string;
}

export interface JournalEntry {
  id: string;
  ts: string;
  kind: "note" | "operation" | "reconciliation";
  text: string;
  amounts: Fee[];
  account_ids: string[];
}

/** POST /v1/journal */
export type JournalInput = Omit<JournalEntry, "id" | "ts">;

export type StreamEventType = "quote.updated" | "source.health" | "opportunity.updated" | "heartbeat" | "source.change" | "alert.fired";

export interface StreamEvent {
  id: string;
  type: StreamEventType;
  ts: string;
  payload: unknown;
}

export interface Snapshot {
  cursor: string;
  server_time: string;
  quotes: Quote[];
  sources: Source[];
  opportunities: Opportunity[];
  data_mode?: DataMode;
}

/** GET /v1/memory */
export interface Memory {
  id: string;
  kind: string;
  text: string;
  tags: string[];
  created_at: string;
  expires_at: string | null;
  source: string;
}

/** GET /v1/memory?q=&kind=&tag=&limit= */
export interface MemoryQuery {
  q: string;
  kind: string;
  tag: string;
  limit: number;
}

/** GET /v1/rag/search → RagHit[] (documentação, tarifas, horários; nunca cotações). */
export interface KnowledgeHit {
  id: string;
  document_id: string;
  title: string | null;
  snippet: string;
  score: number;
  source: string | null;
  tags: string[];
}

export interface KnowledgeQuery {
  q: string;
  k: number;
  tag: string;
}

/** GET /v1/memory/summary?limit= */
export interface MemorySummary {
  summary: string;
}

export interface SimulationRequest {
  capital_brl: string;
  objective: "cycle" | "remittance" | "purchase";
  valuation_currency: Currency;
  channels: Channel[];
  amounts?: string[];
  destination?: Position;
  /** true grava a simulação (`Simulation`/`Opportunity` com data_mode="simulation", D3) e devolve `simulation_id`. */
  persist?: boolean;
}

/** Faixa de capital em que o vencedor ou o sinal do ROI muda (busca adaptativa). */
export interface Boundary {
  low: string;
  high: string;
  low_winner: string | null;
  high_winner: string | null;
  low_roi_sign: string;
  high_roi_sign: string;
  reason: string;
  refined: boolean;
}

export interface SimulationResponse {
  opportunities: Opportunity[];
  search: { amounts_tested: string[]; boundaries: Boundary[] };
  /** Só quando `persist: true`; senão null. */
  simulation_id: string | null;
}

export const CITY_LABEL: Record<Exclude<City, null> | "digital", string> = {
  CDE: "Ciudad del Este",
  ASU: "Asunción",
  PJC: "Pedro Juan Caballero",
  digital: "Digital",
};

export const MODALITY_LABEL: Record<Modality, string> = {
  cash: "Dinheiro físico",
  transfer: "Transferência",
  account: "Conta",
  card_debit: "Cartão de débito",
  card_credit: "Cartão de crédito",
  card_virtual: "Cartão virtual",
  reference: "Referência",
};
