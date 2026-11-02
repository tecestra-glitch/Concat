import { describe, expect, it } from "vitest";
import { applyEdge, edgesFromQuotes, findCycles, nodeKey, roiPerDay, type Edge } from "@/lib/graph";
import { demoEdges, demoParkedBalances } from "@/lib/api/demo-graph";
import type { Quote } from "@/lib/api/types";

const e = (from: string, to: string, rate: number, extra: Partial<Edge> = {}): Edge => ({ from, to, rate, feePct: 0, feeFixed: 0, minutes: 0, via: "t", confidence: "quoted", ...extra });

describe("findCycles", () => {
  it("finds a profitable triangular cycle and computes ROI with the parked amount", () => {
    const edges = [e("USD@a", "PYG@a", 7400), e("PYG@a", "BRL@a", 1 / 1340), e("BRL@a", "USD@a", 1 / 5.4)];
    const cycles = findCycles(edges, { "USD@a": 1000 });
    expect(cycles).toHaveLength(1);
    const c = cycles[0];
    expect(c.amountOut).toBeCloseTo((1000 * 7400) / 1340 / 5.4, 6);
    expect(c.roi).toBeCloseTo(c.gain / 1000, 12);
    expect(c.roi).toBeGreaterThan(0);
  });
  it("fixed and percentage fees reduce the output exactly once per edge", () => {
    expect(applyEdge(100, e("a", "b", 2, { feePct: 0.01, feeFixed: 3 }))).toBeCloseTo(100 * 0.99 * 2 - 3, 10);
  });
  it("ignores 1-edge 'cycles' and repeated nodes", () => {
    const cycles = findCycles([e("a", "a", 1.5), e("a", "b", 1), e("b", "a", 1.01)], { a: 10 });
    expect(cycles.every((c) => c.edges.length >= 2)).toBe(true);
    expect(cycles).toHaveLength(1);
  });
  it("propagates the worst confidence of the path", () => {
    const cycles = findCycles([e("a", "b", 1, { confidence: "incomplete" }), e("b", "a", 1.1)], { a: 10 });
    expect(cycles[0].confidence).toBe("incomplete");
  });
  it("starts only from nodes with parked balance", () => {
    const cycles = findCycles([e("a", "b", 1), e("b", "a", 1.1)], { b: 0, a: 5 });
    expect(cycles.every((c) => c.start === "a")).toBe(true);
  });
  it("roiPerDay annualises by elapsed minutes", () => {
    const [c] = findCycles([e("a", "b", 1, { minutes: 720 }), e("b", "a", 1.01, { minutes: 720 })], { a: 100 });
    expect(roiPerDay(c)).toBeCloseTo(0.01, 10);
  });
});

describe("edgesFromQuotes", () => {
  const q = (over: Partial<Quote>): Quote => ({ id: "q", source_id: "s", branch_id: null, city: null, base: "USD", quote: "PYG", buy: "7300", sell: "7350", unit_note: "", amount_base: null, modality: "account", kind: "indicative", channel: "digital", context: null, fees: [], captured_at: "", declared_updated_at: null, valid_until: null, evidence_id: "ev", data_mode: "demo", ...over });
  it("buy side moves base → quote at buy; sell side moves quote → base at 1/sell", () => {
    const edges = edgesFromQuotes([q({})], () => "s");
    const buy = edges.find((x) => x.from === nodeKey("USD", "s"))!;
    const sell = edges.find((x) => x.from === nodeKey("PYG", "s"))!;
    expect(buy.rate).toBe(7300);
    expect(sell.rate).toBeCloseTo(1 / 7350, 12);
  });
  it("skips market references", () => {
    expect(edgesFromQuotes([q({ kind: "market_reference" })], () => "s")).toHaveLength(0);
  });
});

describe("demo graph", () => {
  it("builds a graph with parked balances and returns cycles sorted by ROI", () => {
    const cycles = findCycles(demoEdges(), demoParkedBalances(), { maxLen: 4 });
    expect(cycles.length).toBeGreaterThan(0);
    for (let i = 1; i < cycles.length; i++) expect(cycles[i - 1].roi).toBeGreaterThanOrEqual(cycles[i].roi);
    expect(Object.keys(demoParkedBalances())).toContain("BRL@brbank");
  });
});
