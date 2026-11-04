import { describe, expect, it } from "vitest";
import { formatCheckedAt, institutionCurrencies, InstitutionSchema, sourceLabel, sourceHost, type Institution } from "./institutions";

const base: Institution = {
  id: "wise",
  name: "Wise",
  country: "BR",
  kind: "fintech",
  status: "active",
  discontinued_note: null,
  currencies_held: ["BRL", "USD", "EUR"],
  opens_remotely: null,
  requires: null,
  api: "pf",
  api_source_url: "https://docs.wise.com/x",
  source_url: "https://wise.com/help/articles/2897238/x",
  checked_at: "2026-11-04",
  fx_cost: {
    spread_pct: { value: null, currency: null, source_url: null, checked_at: null, note: null },
    iof_pct: { value: "0.035", currency: null, source_url: "https://wise.com/help/articles/2932353/transfers-to-brl", checked_at: "2026-11-04", note: null },
    fee_pct: { value: null, currency: null, source_url: null, checked_at: null, note: null },
    fee_fixed: { value: null, currency: null, source_url: null, checked_at: null, note: null },
  },
};

describe("cadastro de instituições", () => {
  it("aceita o formato da API e rejeita número JSON no lugar de decimal", () => {
    expect(InstitutionSchema.parse(base).id).toBe("wise");
    const bad = { ...base, fx_cost: { ...base.fx_cost, iof_pct: { ...base.fx_cost.iof_pct, value: 0.035 } } };
    expect(InstitutionSchema.safeParse(bad).success).toBe(false);
  });

  it("moedas do selo ficam só com as que o app representa", () => {
    expect(institutionCurrencies(base)).toEqual(["BRL", "USD"]);
    expect(institutionCurrencies({ ...base, currencies_held: null })).toEqual([]);
  });

  it("selo de fonte mostra domínio e data em pt-BR; sem fonte, sem selo", () => {
    expect(sourceLabel(base.fx_cost.iof_pct)).toBe("fonte: wise.com · 04/11/2026");
    expect(sourceLabel(base.fx_cost.spread_pct)).toBeNull();
  });

  it("formatCheckedAt e sourceHost não quebram com entrada ruim", () => {
    expect(formatCheckedAt("04-11-2026")).toBeNull();
    expect(sourceHost("não é url")).toBeNull();
    expect(sourceHost("https://www.bancobasa.com.py/")).toBe("bancobasa.com.py");
  });
});
