/**
 * zod schemas mirroring docs/api-contract.md (D1/D2/D3). Money stays a decimal string.
 * Use them at the boundaries where a payload is untrusted (SSE payloads, proxy responses).
 */
import { z } from "zod";

export const ModeSchema = z.enum(["real", "simulation", "demo"]);

/** Canonical decimal string: optional sign, digits, optional fraction. Never a float. */
export const DecimalString = z.string().regex(/^-?\d+(\.\d+)?$/, "esperado decimal em string");

const NullableDecimalString = DecimalString.nullable();

export const ConfidenceSchema = z.enum(["quoted", "estimated", "incomplete"]);
export const CurrencySchema = z.enum(["BRL", "USD", "PYG"]);
export const CitySchema = z.enum(["CDE", "ASU", "PJC", "FOZ", "ENC"]).nullable();
export const ChannelSchema = z.enum(["digital", "physical", "aggregator"]);
export const ModalitySchema = z.enum(["cash", "transfer", "account", "card_debit", "card_credit", "card_virtual", "reference"]);
export const QuoteKindSchema = z.enum(["market_reference", "indicative", "executable"]);

/** Fixed (`amount`) and/or percentage over the input (`pct`); either may be null (contract `Fee`). */
export const FeeSchema = z.object({
  label: z.string(),
  amount: NullableDecimalString,
  currency: CurrencySchema,
  pct: NullableDecimalString.optional(),
});

export const RouteChannelSchema = z.enum(["presencial", "assistida", "automatizavel"]);
export const EdgeKindSchema = z.enum(["quote", "transfer", "deposit", "withdraw", "travel"]);
export const LegKindSchema = z.enum(["exchange", "transfer", "travel", "deposit", "withdraw"]);

export const EdgeSchema = z.object({
  from: z.string(),
  to: z.string(),
  kind: EdgeKindSchema,
  rate: DecimalString,
  fee_pct: DecimalString,
  fee_fixed: DecimalString,
  minutes: z.number(),
  via: z.string(),
  confidence: ConfidenceSchema,
  evidence_id: z.string().nullable(),
  channel: RouteChannelSchema,
  iof_pct: DecimalString.optional(),
  transport_fixed: DecimalString.optional(),
  border: z.boolean().optional(),
  counter: z.boolean().optional(),
  ref_rate: NullableDecimalString.optional(),
  quoted_at: z.string().nullable().optional(),
  unknown_costs: z.array(z.enum(["spread", "fees", "iof", "transport"])).optional(),
});

/** Custos de uma perna na moeda em que ela começou; `null` = desconhecido (nunca zero). */
export const LegCostsSchema = z.object({
  currency: CurrencySchema,
  spread: NullableDecimalString,
  fees: NullableDecimalString,
  iof: NullableDecimalString,
  transport: NullableDecimalString,
});

export const LegSchema = z.object({
  kind: LegKindSchema,
  channel: RouteChannelSchema,
  from: z.string(),
  to: z.string(),
  via: z.string(),
  minutes: z.number(),
  border: z.boolean(),
  amount_in: DecimalString,
  amount_out: DecimalString,
  costs: LegCostsSchema,
});

export const GainByCurrencySchema = z.object({ BRL: NullableDecimalString, USD: NullableDecimalString, PYG: NullableDecimalString });

export const CycleSchema = z.object({
  start: z.string(),
  path: z.array(z.string()),
  edges: z.array(EdgeSchema),
  legs: z.array(LegSchema),
  amount_in: DecimalString,
  amount_out: DecimalString,
  gain: DecimalString,
  roi: DecimalString,
  gain_by_currency: GainByCurrencySchema.nullable(),
  costs: z.object({ spread: NullableDecimalString, fees: NullableDecimalString, iof: NullableDecimalString, transport: NullableDecimalString }).nullable(),
  requires_declaration: z.boolean(),
  minutes: z.number(),
  confidence: ConfidenceSchema,
  data_mode: ModeSchema,
});

export const PlanStatusSchema = z.enum(["proposed", "approved", "in_progress", "done", "rejected", "expired"]);

export const PlanStepSchema = z.object({
  n: z.number().int().positive(),
  kind: LegKindSchema,
  channel: RouteChannelSchema,
  text: z.string(),
  from: z.string(),
  to: z.string(),
  amount_in: DecimalString,
  amount_out_expected: DecimalString,
  minutes: z.number(),
  status: z.enum(["pending", "done"]),
  actual_out: NullableDecimalString,
  note: z.string().nullable(),
  done_at: z.string().nullable(),
});

/** PlanOut (docs/api-contract.md, "Planos de execução"). */
export const PlanSchema = z.object({
  id: z.string(),
  status: PlanStatusSchema,
  start: z.string(),
  path: z.array(z.string()),
  currency: CurrencySchema,
  amount_in: DecimalString,
  amount_out_expected: DecimalString,
  gain_expected: DecimalString,
  gain_by_currency: GainByCurrencySchema.nullable(),
  confidence: ConfidenceSchema,
  minutes: z.number(),
  requires_declaration: z.boolean(),
  quotes_as_of: z.string(),
  quote_max_age_s: z.number().int().positive(),
  created_at: z.string(),
  decided_at: z.string().nullable(),
  completed_at: z.string().nullable(),
  data_mode: ModeSchema,
  costs: z.object({ spread: NullableDecimalString, fees: NullableDecimalString, iof: NullableDecimalString, transport: NullableDecimalString }).nullish(),
  steps: z.array(PlanStepSchema),
});

export const QuoteSchema = z.object({
  id: z.string(),
  series_key: z.string(),
  source_id: z.string(),
  branch_id: z.string().nullable(),
  city: CitySchema,
  base: CurrencySchema,
  quote: CurrencySchema,
  buy: NullableDecimalString,
  sell: NullableDecimalString,
  unit_note: z.string(),
  amount_base: NullableDecimalString,
  modality: ModalitySchema,
  kind: QuoteKindSchema,
  channel: ChannelSchema,
  context: z.record(z.string(), z.string().nullable()).nullable(),
  fees: z.array(FeeSchema),
  captured_at: z.string(),
  declared_updated_at: z.string().nullable(),
  valid_until: z.string().nullable(),
  evidence_id: z.string().nullable(),
  data_mode: ModeSchema,
});

export const StreamEventTypeSchema = z.enum(["quote.updated", "source.health", "opportunity.updated", "heartbeat", "source.change", "alert.fired", "market.news", "market.volatility_alert"]);

export const StreamEventSchema = z.object({
  id: z.string(),
  type: StreamEventTypeSchema,
  ts: z.string(),
  payload: z.unknown(),
});

export const SourceHealthStateSchema = z.enum(["ok", "degraded", "blocked", "stale", "unknown"]);

/** Como a fonte é alcançada (`integration` em GET /v1/sources): selo na tela de Fontes. */
export const SourceIntegrationSchema = z.enum(["api_oficial", "endpoint_interno", "html", "navegador"]);

/**
 * Payload of `source.health` (Q-02): a partial update keyed by `source_id`, never a full `Source`.
 * Emitted by services/collector.py (with `next_poll_at`) and services/demo.py (without it).
 */
export const SourceHealthEventSchema = z.object({
  source_id: z.string().min(1),
  health: SourceHealthStateSchema,
  last_error: z.string().nullable(),
  consecutive_failures: z.number().int().nonnegative().optional(),
  next_poll_at: z.string().nullable().optional(),
});

export const HealthSchema = z.object({
  status: z.string(),
  data_mode: ModeSchema,
  db: z.string().optional(),
  version: z.string().optional(),
  server_time: z.string().optional(),
});

export type ParsedQuote = z.infer<typeof QuoteSchema>;
export type ParsedCycle = z.infer<typeof CycleSchema>;
export type ParsedPlan = z.infer<typeof PlanSchema>;
export type ParsedEdge = z.infer<typeof EdgeSchema>;
export type ParsedStreamEvent = z.infer<typeof StreamEventSchema>;
export type ParsedHealth = z.infer<typeof HealthSchema>;
export type SourceHealthEvent = z.infer<typeof SourceHealthEventSchema>;
