import { describe, expect, it } from "vitest";
import { CycleSchema, EdgeSchema, FeeSchema, HealthSchema, ModeSchema, PlanSchema, QuoteSchema, StreamEventSchema } from "@/lib/api/schemas";

const edge = { from: "BRL@brbank", to: "PYG@banco-demo-py", kind: "transfer", rate: "1360.8", fee_pct: "0", fee_fixed: "0", minutes: 2880, via: "Western Union", confidence: "estimated", evidence_id: null, channel: "assistida" };
const leg = { kind: "transfer", channel: "assistida", from: "BRL@brbank", to: "PYG@banco-demo-py", via: "Western Union", minutes: 2880, border: false, amount_in: "25000", amount_out: "34000000", costs: { currency: "BRL", spread: null, fees: "0", iof: null, transport: null } };
const cycle = { start: "BRL@brbank", path: ["BRL@brbank", "PYG@banco-demo-py", "BRL@brbank"], edges: [edge, { ...edge, from: "PYG@banco-demo-py", to: "BRL@brbank" }], legs: [leg], amount_in: "25000", amount_out: "25041.20", gain: "41.20", roi: "0.001648", gain_by_currency: { BRL: "41.20", USD: "7.60", PYG: "55000" }, costs: { spread: null, fees: "0", iof: null, transport: null }, requires_declaration: false, minutes: 4320, confidence: "estimated", data_mode: "real" };

describe("zod schemas mirror the contract", () => {
  it("Fee is fixed and/or percentage: amount may be null, pct optional (Q-03/MED-03)", () => {
    const pctOnly = { label: "spread", amount: null, currency: "BRL", pct: "0.015" };
    expect(FeeSchema.parse(pctOnly)).toEqual(pctOnly);
    expect(FeeSchema.parse({ label: "tarifa", amount: "9.9", currency: "BRL" })).toEqual({ label: "tarifa", amount: "9.9", currency: "BRL" });
    expect(FeeSchema.parse({ label: "tarifa", amount: "9.9", currency: "BRL", pct: null }).pct).toBeNull();
    expect(FeeSchema.safeParse({ label: "x", amount: 9.9, currency: "BRL" }).success).toBe(false);
  });
  it("Mode accepts the three data modes only", () => {
    expect(ModeSchema.parse("simulation")).toBe("simulation");
    expect(ModeSchema.safeParse("auto").success).toBe(false);
  });
  it("Edge and Cycle use decimal strings (D1)", () => {
    expect(EdgeSchema.parse(edge)).toEqual(edge);
    expect(CycleSchema.parse(cycle)).toEqual(cycle);
    expect(CycleSchema.safeParse({ ...cycle, amount_in: 25000 }).success).toBe(false);
    expect(CycleSchema.safeParse({ ...cycle, amountIn: "25000", amount_in: undefined }).success).toBe(false);
    expect(EdgeSchema.safeParse({ ...edge, rate: "abc" }).success).toBe(false);
  });
  it("Quote requires series_key (D2)", () => {
    const quote = { id: "q", series_key: "chaco:CDE:USD/PYG:cash", source_id: "chaco", branch_id: null, city: "CDE", base: "USD", quote: "PYG", buy: "7300", sell: "7350", unit_note: "", amount_base: null, modality: "cash", kind: "executable", channel: "physical", context: null, fees: [], captured_at: "2026-11-02T12:00:00Z", declared_updated_at: null, valid_until: null, evidence_id: null, data_mode: "real" };
    expect(QuoteSchema.parse(quote).series_key).toBe("chaco:CDE:USD/PYG:cash");
    const { series_key: _omit, ...without } = quote;
    void _omit;
    expect(QuoteSchema.safeParse(without).success).toBe(false);
  });
  it("Quote accepts third-party reference vocabulary (dolarPy: modality=reference, channel=aggregator)", () => {
    const ref = { id: "r", series_key: "dolarpy:digital:USD/PYG:reference:@dolarpy-bcp:1a2b3c4d", source_id: "dolarpy", branch_id: "dolarpy-bcp", city: null, base: "USD", quote: "PYG", buy: "7290", sell: "7360", unit_note: "referência de terceiro, não executável", amount_base: null, modality: "reference", kind: "market_reference", channel: "aggregator", context: { aggregator: "dolarpy", house: "bcp" }, fees: [], captured_at: "2026-11-02T12:00:00Z", declared_updated_at: null, valid_until: null, evidence_id: null, data_mode: "real" };
    const parsed = QuoteSchema.parse(ref);
    expect(parsed.modality).toBe("reference");
    expect(parsed.channel).toBe("aggregator");
    expect(QuoteSchema.safeParse({ ...ref, channel: "telepathic" }).success).toBe(false);
  });
  it("Edge kinds mirror the contract (quote | transfer | deposit | withdraw)", () => {
    for (const kind of ["quote", "transfer", "deposit", "withdraw"]) {
      expect(EdgeSchema.parse({ ...edge, kind }).kind).toBe(kind);
    }
    expect(EdgeSchema.safeParse({ ...edge, kind: "teleport" }).success).toBe(false);
    expect(EdgeSchema.safeParse({ ...edge, kind: "travel", channel: "presencial" }).success).toBe(true);
    expect(EdgeSchema.safeParse({ ...edge, channel: "de-carro" }).success).toBe(false);
  });
  it("StreamEvent knows source.change and alert.fired", () => {
    for (const type of ["quote.updated", "source.health", "opportunity.updated", "heartbeat", "source.change", "alert.fired"]) {
      expect(StreamEventSchema.parse({ id: "1", type, ts: "2026-11-02T12:00:00Z", payload: {} }).type).toBe(type);
    }
    expect(StreamEventSchema.safeParse({ id: "1", type: "unknown.event", ts: "x", payload: {} }).success).toBe(false);
  });
  it("Health carries data_mode", () => {
    expect(HealthSchema.parse({ status: "ok", data_mode: "simulation", db: "ok", version: "0.1.0" }).data_mode).toBe("simulation");
    expect(HealthSchema.safeParse({ status: "ok" }).success).toBe(false);
  });
});

describe("contrato v2: pernas, ganho por moeda e planos", () => {
  it("CycleSchema aceita legs, gain_by_currency com null e costs com null", () => {
    expect(CycleSchema.parse({ ...cycle, gain_by_currency: { BRL: "41.20", USD: null, PYG: null } }).gain_by_currency?.USD).toBeNull();
    expect(CycleSchema.safeParse({ ...cycle, legs: [{ ...leg, channel: "robô" }] }).success).toBe(false);
    expect(CycleSchema.safeParse({ ...cycle, legs: [{ ...leg, costs: { ...leg.costs, fees: 0 } }] }).success).toBe(false);
  });
  it("PlanSchema aceita só os seis estados e passos com valores em string decimal", () => {
    const plan = {
      id: "p1", status: "proposed", start: "BRL@brbank", path: ["BRL@brbank", "BRL@brbank"], currency: "BRL",
      amount_in: "5000", amount_out_expected: "5042.1", gain_expected: "42.1", gain_by_currency: { BRL: "42.1", USD: "7.8", PYG: "46000" },
      confidence: "quoted", minutes: 60, requires_declaration: false, quotes_as_of: "2026-11-04T12:00:00Z", quote_max_age_s: 900,
      created_at: "2026-11-04T12:00:00Z", decided_at: null, completed_at: null, data_mode: "demo",
      steps: [{ n: 1, kind: "travel", channel: "presencial", text: "Leve o dinheiro", from: "BRL@cash:CDE", to: "BRL@cash:ASU", amount_in: "5000", amount_out_expected: "5000", minutes: 240, status: "pending", actual_out: null, note: null, done_at: null }],
    };
    expect(PlanSchema.parse(plan).steps[0].status).toBe("pending");
    expect(PlanSchema.safeParse({ ...plan, status: "concluido" }).success).toBe(false);
    expect(PlanSchema.safeParse({ ...plan, steps: [{ ...plan.steps[0], actual_out: 5000 }] }).success).toBe(false);
  });
});
