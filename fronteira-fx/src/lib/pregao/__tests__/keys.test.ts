import { describe, expect, it } from "vitest";
import { allDemoQuotes } from "@/lib/api/demo-data";
import { quoteKey } from "@/lib/pregao/keys";

const base = { source_id: "chaco", city: "CDE" as const, base: "USD" as const, quote: "PYG" as const, modality: "cash" as const, branch_id: null, amount_base: null };

describe("quoteKey", () => {
  it("uses Quote.series_key when present (D2)", () => {
    expect(quoteKey({ ...base, series_key: "chaco:CDE:USD/PYG:cash:@chaco-cde-centro" })).toBe("chaco:CDE:USD/PYG:cash:@chaco-cde-centro");
    for (const q of allDemoQuotes) expect(quoteKey(q)).toBe(q.series_key);
  });

  it("falls back to the D2 shape without the context hash when series_key is missing or empty", () => {
    expect(quoteKey(base)).toBe("chaco:CDE:USD/PYG:cash");
    expect(quoteKey({ ...base, series_key: "" })).toBe("chaco:CDE:USD/PYG:cash");
    expect(quoteKey({ ...base, series_key: null, branch_id: "chaco-cde-centro", amount_base: "5000" })).toBe("chaco:CDE:USD/PYG:cash:@chaco-cde-centro:5000");
    expect(quoteKey({ ...base, city: null, modality: "account", source_id: "banco-demo-py" })).toBe("banco-demo-py:digital:USD/PYG:account");
  });
});
