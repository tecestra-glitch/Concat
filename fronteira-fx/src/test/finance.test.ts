import { describe, expect, it } from "vitest";
import { PHYSICAL_THRESHOLD, rankOpportunities, runRoute } from "@/lib/finance";
import type { Opportunity } from "@/lib/api/types";

const pos = (currency: "BRL" | "USD" | "PYG") => ({ currency, account_id: null, location: "digital", modality: "account" as const, amount: "0" });

describe("runRoute", () => {
  it("chains each step on the previous output and never double counts fees", () => {
    const r = runRoute(5000, [
      { description: "a", rate: 1080.3742, rateNote: "", feeIn: [{ label: "tarifa", amount: "0", currency: "BRL" }], duration: "", from: pos("BRL"), to: pos("PYG") },
      { description: "b", rate: 1 / 7400, rateNote: "", feeOut: [{ label: "x", amount: "1", currency: "USD" }], duration: "", from: pos("PYG"), to: pos("USD") },
    ]);
    expect(r.steps[0].amount_out).toBe(String(5000 * 1080.3742));
    expect(Number(r.steps[1].amount_out)).toBeCloseTo((5000 * 1080.3742) / 7400 - 1, 6);
    expect(r.steps.flatMap((s) => s.fees)).toHaveLength(2);
    expect(r.confidence).toBe("quoted");
  });
  it("marks unknown essential costs as incomplete", () => {
    const r = runRoute(1000, [{ description: "a", rate: 1, rateNote: "", unknownFee: "IOF", duration: "", from: pos("BRL"), to: pos("BRL") }]);
    expect(r.confidence).toBe("incomplete");
    expect(r.pending).toEqual(["IOF"]);
  });
  it("different amount gives different result", () => {
    const a = runRoute(5000, [{ description: "a", rate: 1.01, rateNote: "", duration: "", from: pos("BRL"), to: pos("BRL") }]).final;
    const b = runRoute(10000, [{ description: "a", rate: 1.01, rateNote: "", duration: "", from: pos("BRL"), to: pos("BRL") }]).final;
    expect(a).not.toBe(b);
  });
});

function opp(id: string, channel: "digital" | "physical", gain: number, capital = 5000): Opportunity {
  return { id, title: id, kind: "cycle", channel, city: channel === "physical" ? "CDE" : null, capital_brl: String(capital), final_value_brl: String(capital + gain), net_gain_brl: String(gain), roi: String(gain / capital), effective_rate: "1", valuation_currency: "BRL", steps: [], confidence: "quoted", pending_costs: [], in_main_ranking: false, ranking_reason: "", comparable_best_digital_roi: null, computed_at: "", data_mode: "demo" };
}

describe("rankOpportunities", () => {
  it("keeps a digital micro-gain in the main ranking", () => {
    const [r] = rankOpportunities([opp("d", "digital", 0.37)]);
    expect(r.in_main_ranking).toBe(true);
  });
  it("excludes digital routes without gain", () => {
    const [r] = rankOpportunities([opp("d", "digital", -0.01)]);
    expect(r.in_main_ranking).toBe(false);
  });
  it("physical enters only at >= best digital + 1 p.p.", () => {
    const digital = opp("d", "digital", 50); // roi 1%
    const exactly = opp("p1", "physical", 5000 * (0.01 + PHYSICAL_THRESHOLD)); // roi 2%
    const below = opp("p2", "physical", 5000 * (0.01 + PHYSICAL_THRESHOLD) - 0.01);
    const ranked = rankOpportunities([digital, exactly, below]);
    expect(ranked.find((o) => o.id === "p1")!.in_main_ranking).toBe(true);
    expect(ranked.find((o) => o.id === "p2")!.in_main_ranking).toBe(false);
    expect(ranked.find((o) => o.id === "p2")!.ranking_reason).toMatch(/abaixo do limite/);
  });
  it("physical with negative gain stays out even if digital is worse", () => {
    const ranked = rankOpportunities([opp("d", "digital", -300), opp("p", "physical", -50)]);
    expect(ranked.find((o) => o.id === "p")!.in_main_ranking).toBe(false);
    expect(ranked.find((o) => o.id === "p")!.ranking_reason).toMatch(/sem ganho/);
  });
  it("sorts by roi desc", () => {
    const ranked = rankOpportunities([opp("a", "digital", 1), opp("b", "digital", 10)]);
    expect(ranked[0].id).toBe("b");
  });
});
