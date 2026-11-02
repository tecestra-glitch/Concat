import { describe, expect, it } from "vitest";
import { applyEdge, dec, edgesFromQuotes, findCycles, nodeKey, roiPerDay, type Edge } from "@/lib/graph";
import { demoEdges, demoParkedBalances } from "@/lib/api/demo-graph";
import type { Quote } from "@/lib/api/types";

const e = (from: string, to: string, rate: number | string, extra: Partial<Edge> = {}): Edge => ({
  from,
  to,
  kind: "transfer",
  rate: String(rate),
  fee_pct: "0",
  fee_fixed: "0",
  minutes: 0,
  via: "t",
  confidence: "quoted",
  evidence_id: null,
  ...extra,
});

describe("findCycles (D1: decimal strings, snake_case, data_mode)", () => {
  it("finds a profitable triangular cycle and computes ROI with the parked amount", () => {
    const edges = [e("USD@a", "PYG@a", 7400), e("PYG@a", "BRL@a", 1 / 1340), e("BRL@a", "USD@a", 1 / 5.4)];
    const cycles = findCycles(edges, { "USD@a": "1000" });
    expect(cycles).toHaveLength(1);
    const c = cycles[0];
    expect(typeof c.amount_in).toBe("string");
    expect(c.amount_in).toBe("1000");
    expect(Number(c.amount_out)).toBeCloseTo((1000 * 7400) / 1340 / 5.4, 6);
    expect(Number(c.roi)).toBeCloseTo(Number(c.gain) / 1000, 10);
    expect(Number(c.roi)).toBeGreaterThan(0);
    expect(c.path).toEqual(["USD@a", "PYG@a", "BRL@a", "USD@a"]);
    expect(c.data_mode).toBe("demo");
    expect(c.edges[0].rate).toBe("7400");
  });
  it("fixed and percentage fees reduce the output exactly once per edge", () => {
    expect(applyEdge(100, e("a", "b", 2, { fee_pct: "0.01", fee_fixed: "3" }))).toBeCloseTo(100 * 0.99 * 2 - 3, 10);
  });
  it("ignores 1-edge 'cycles' and repeated nodes", () => {
    const cycles = findCycles([e("a", "a", 1.5), e("a", "b", 1), e("b", "a", 1.01)], { a: "10" });
    expect(cycles.every((c) => c.edges.length >= 2)).toBe(true);
    expect(cycles).toHaveLength(1);
  });
  it("propagates the worst confidence of the path", () => {
    const cycles = findCycles([e("a", "b", 1, { confidence: "incomplete" }), e("b", "a", 1.1)], { a: "10" });
    expect(cycles[0].confidence).toBe("incomplete");
  });
  it("starts only from nodes with parked balance", () => {
    const cycles = findCycles([e("a", "b", 1), e("b", "a", 1.1)], { b: "0", a: "5" });
    expect(cycles.every((c) => c.start === "a")).toBe(true);
  });
  it("applies min_roi as a decimal string and keeps the data_mode asked", () => {
    const edges = [e("a", "b", 1), e("b", "a", 1.1)];
    expect(findCycles(edges, { a: "10" }, { minRoi: "0.5" })).toHaveLength(0);
    expect(findCycles(edges, { a: "10" }, { minRoi: "0.05", dataMode: "simulation" })[0].data_mode).toBe("simulation");
  });
  it("roiPerDay annualises by elapsed minutes", () => {
    const [c] = findCycles([e("a", "b", 1, { minutes: 720 }), e("b", "a", 1.01, { minutes: 720 })], { a: "100" });
    expect(roiPerDay(c)).toBeCloseTo(0.01, 10);
  });
});

describe("edgesFromQuotes", () => {
  const q = (over: Partial<Quote>): Quote => ({ id: "q", series_key: "s:digital:USD/PYG:account", source_id: "s", branch_id: null, city: null, base: "USD", quote: "PYG", buy: "7300", sell: "7350", unit_note: "", amount_base: null, modality: "account", kind: "indicative", channel: "digital", context: null, fees: [], captured_at: "", declared_updated_at: null, valid_until: null, evidence_id: "ev", data_mode: "demo", ...over });
  it("buy side moves base → quote at buy; sell side moves quote → base at 1/sell", () => {
    const edges = edgesFromQuotes([q({})], () => "s");
    const buy = edges.find((x) => x.from === nodeKey("USD", "s"))!;
    const sell = edges.find((x) => x.from === nodeKey("PYG", "s"))!;
    expect(buy.rate).toBe("7300");
    expect(buy.kind).toBe("quote");
    expect(buy.evidence_id).toBe("ev");
    expect(Number(sell.rate)).toBeCloseTo(1 / 7350, 12);
  });
  it("skips market references", () => {
    expect(edgesFromQuotes([q({ kind: "market_reference" })], () => "s")).toHaveLength(0);
  });
});

describe("demo graph", () => {
  it("builds a graph with parked balances (decimal strings) and returns cycles sorted by ROI", () => {
    const balances = demoParkedBalances();
    expect(Object.keys(balances)).toContain("BRL@brbank");
    expect(Object.values(balances).every((v) => typeof v === "string")).toBe(true);
    const cycles = findCycles(demoEdges(), balances, { maxLen: 4 });
    expect(cycles.length).toBeGreaterThan(0);
    for (let i = 1; i < cycles.length; i++) expect(Number(cycles[i - 1].roi)).toBeGreaterThanOrEqual(Number(cycles[i].roi));
    expect(demoEdges().every((x) => typeof x.rate === "string" && typeof x.fee_pct === "string" && typeof x.fee_fixed === "string")).toBe(true);
  });
});

describe("dec", () => {
  it("emits a plain decimal string, never exponent notation, even for huge amounts", () => {
    expect(dec(0.1 + 0.2)).toBe("0.3");
    expect(dec(-0)).toBe("0");
    expect(dec(1e21)).toBe("1000000000000000000000");
    expect(dec(-1e21)).toBe("-1000000000000000000000");
    expect(dec(1.5e22, 8)).toMatch(/^-?\d+(\.\d+)?$/);
  });
});
