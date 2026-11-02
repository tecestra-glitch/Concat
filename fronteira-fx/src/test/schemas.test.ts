import { describe, expect, it } from "vitest";
import { CycleSchema, EdgeSchema, HealthSchema, ModeSchema, QuoteSchema, StreamEventSchema } from "@/lib/api/schemas";

const edge = { from: "BRL@brbank", to: "PYG@ueno", kind: "transfer", rate: "1360.8", fee_pct: "0", fee_fixed: "0", minutes: 2880, via: "Western Union", confidence: "estimated", evidence_id: null };
const cycle = { start: "BRL@brbank", path: ["BRL@brbank", "PYG@ueno", "BRL@brbank"], edges: [edge, { ...edge, from: "PYG@ueno", to: "BRL@brbank" }], amount_in: "25000", amount_out: "25041.20", gain: "41.20", roi: "0.001648", minutes: 4320, confidence: "estimated", data_mode: "real" };

describe("zod schemas mirror the contract", () => {
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
