/** Mirrors docs/api-contract.md. Money travels as decimal strings. */
export type Currency = "BRL" | "USD" | "PYG";
export type City = "CDE" | "ASU" | "PJC" | null;
export type Channel = "digital" | "physical";
export type Modality = "cash" | "transfer" | "account" | "card_debit" | "card_credit" | "card_virtual";
export type QuoteKind = "market_reference" | "indicative" | "executable";
export type SourceMethod = "official_api" | "html" | "browser" | "manual";
export type Health = "ok" | "degraded" | "blocked" | "stale" | "unknown";
export type Confidence = "quoted" | "estimated" | "incomplete";
export type DataMode = "real" | "simulation" | "demo";
export type OpportunityKind = "cycle" | "remittance_saving" | "purchase_saving";

export interface Fee {
  label: string;
  amount: string;
  currency: Currency;
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
  evidence_id: string;
  data_mode: DataMode;
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

export interface JournalEntry {
  id: string;
  ts: string;
  kind: "note" | "operation" | "reconciliation";
  text: string;
  amounts: Fee[];
  account_ids: string[];
}

export interface StreamEvent {
  id: string;
  type: "quote.updated" | "source.health" | "opportunity.updated" | "heartbeat";
  ts: string;
  payload: unknown;
}

export interface Snapshot {
  cursor: string;
  server_time: string;
  quotes: Quote[];
  sources: Source[];
  opportunities: Opportunity[];
}

export interface SimulationRequest {
  capital_brl: string;
  objective: "cycle" | "remittance" | "purchase";
  valuation_currency: Currency;
  channels: Channel[];
  amounts?: string[];
  destination?: Position;
}

export interface SimulationResponse {
  opportunities: Opportunity[];
  search: { amounts_tested: string[]; boundaries: string[] };
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
};
