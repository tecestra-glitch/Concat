import { describe, expect, it } from "vitest";
import { WU_HISTORICAL_FIXTURE, allDemoQuotes, demoOpportunities, demoWesternUnionQuotes } from "@/lib/api/demo-data";

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
