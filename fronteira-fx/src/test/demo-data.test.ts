import { describe, expect, it } from "vitest";
import { WU_HISTORICAL_FIXTURE, allDemoQuotes, demoHistory, demoOpportunities, demoWesternUnionQuotes, seriesKey } from "@/lib/api/demo-data";

describe("demo dataset isolation", () => {
  it("every demo record is flagged data_mode=demo", () => {
    expect(allDemoQuotes.every((q) => q.data_mode === "demo")).toBe(true);
    expect(demoOpportunities.every((o) => o.data_mode === "demo")).toBe(true);
  });
  it("Western Union receive methods are separate quotes with separate contexts", () => {
    const bank = demoWesternUnionQuotes.find((q) => q.amount_base === "5000" && q.context?.receive === "bank_account")!;
    const cash = demoWesternUnionQuotes.find((q) => q.amount_base === "5000" && q.context?.receive === "cash_pickup")!;
    expect(bank.id).not.toBe(cash.id);
    expect(Number(bank.sell)).toBeGreaterThan(Number(cash.sell));
    expect(bank.context?.duration).not.toBe(cash.context?.duration);
  });
  it("historical WU fixture is labelled and never served as a demo quote", () => {
    expect(WU_HISTORICAL_FIXTURE.note).toMatch(/histórico/);
    expect(allDemoQuotes.some((q) => Number(q.sell) * 5000 === WU_HISTORICAL_FIXTURE.bank_account.receive_pyg)).toBe(false);
  });
  it("main ranking never contains a negative net gain", () => {
    expect(demoOpportunities.filter((o) => o.in_main_ranking).every((o) => Number(o.net_gain_brl) > 0)).toBe(true);
  });
  it("digital opportunities never carry an invented city", () => {
    expect(demoOpportunities.filter((o) => o.channel === "digital").every((o) => o.city === null)).toBe(true);
  });
  it("purchase scenario stays an incomplete estimate until card charges are validated", () => {
    expect(demoOpportunities.filter((o) => o.kind === "purchase_saving").every((o) => o.confidence === "incomplete")).toBe(true);
  });
});

describe("series_key (D2) in the demo dataset", () => {
  it("every quote carries series_key in the backend format source:city|digital:BASE/QUOTE:modality[:@branch][:amount][:ctx8]", () => {
    for (const q of allDemoQuotes) {
      expect(q.series_key).toBe(seriesKey(q));
      const prefix = `${q.source_id}:${q.city ?? "digital"}:${q.base}/${q.quote}:${q.modality}`;
      expect(q.series_key.startsWith(prefix)).toBe(true);
      const rest = q.series_key.slice(prefix.length);
      if (q.amount_base === null && !q.context && !q.branch_id) expect(rest).toBe("");
      if (q.branch_id) expect(rest).toContain(`:@${q.branch_id}`);
      if (q.amount_base !== null) expect(rest).toContain(`:${q.amount_base}`);
      if (q.context && Object.keys(q.context).length > 0) expect(rest).toMatch(/:[0-9a-f]{8}$/);
    }
  });
  it("keys are unique per quote and differ between contexts of the same amount", () => {
    expect(new Set(allDemoQuotes.map((q) => q.series_key)).size).toBe(allDemoQuotes.length);
    const bank = demoWesternUnionQuotes.find((q) => q.amount_base === "5000" && q.context?.receive === "bank_account")!;
    const cash = demoWesternUnionQuotes.find((q) => q.amount_base === "5000" && q.context?.receive === "cash_pickup")!;
    expect(bank.series_key).toMatch(/^westernunion:digital:BRL\/PYG:account:5000:[0-9a-f]{8}$/);
    expect(cash.series_key).toMatch(/^westernunion:digital:BRL\/PYG:cash:5000:[0-9a-f]{8}$/);
    expect(bank.series_key).not.toBe(cash.series_key);
  });
  it("history is addressed by the same key and echoes it", () => {
    const q = allDemoQuotes[3];
    const h = demoHistory(q.series_key, 12);
    expect(h.key).toBe(q.series_key);
    expect(h.points).toHaveLength(12);
  });
  it("history for an unknown key is empty and still echoes the key (no silent fallback to another series)", () => {
    const h = demoHistory("nope:XX:USD/PYG:cash", 12);
    expect(h.key).toBe("nope:XX:USD/PYG:cash");
    expect(h.points).toHaveLength(0);
  });
});

describe("demo simulation mirrors SimulationResponse (MED-02)", () => {
  it("boundaries are Boundary objects and simulation_id is present (null: nothing persisted)", async () => {
    const { simulateDemo } = await import("@/lib/api/demo-simulate");
    const res = await simulateDemo({ capital_brl: "5000", objective: "cycle", valuation_currency: "BRL", channels: ["digital", "physical"] });
    expect(res.simulation_id).toBeNull();
    expect(res.search.boundaries.length).toBeGreaterThan(0);
    for (const b of res.search.boundaries) {
      expect(typeof b.low).toBe("string");
      expect(typeof b.high).toBe("string");
      expect(typeof b.reason).toBe("string");
    }
  });
});

describe("demonstração sem o banco fechado (resolução pelo BCP em 03/11/2026)", () => {
  it("o banco fechado não aparece em contas; Revolut e Nomad são contas digitais", async () => {
    const { demoAccounts } = await import("@/lib/api/demo-data");
    const revolut = demoAccounts.filter((a) => a.institution === "Revolut");
    expect(revolut.map((a) => a.currency).sort()).toEqual(["BRL", "USD"]);
    expect(revolut.every((a) => a.location === "digital")).toBe(true);
    expect(demoAccounts.some((a) => a.institution === "Nomad" && a.currency === "USD")).toBe(true);
    expect(demoAccounts.some((a) => a.currency === "PYG" && a.institution === "Revolut")).toBe(false);
  });
});
