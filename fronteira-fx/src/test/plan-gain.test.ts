import { describe, expect, it } from "vitest";
import { formatPlanCountdown, gainPresentation, unknownCostLabels } from "@/components/planos/plan-helpers";

describe("ganho do plano: nunca lucro confirmado quando há custo pendente (M4, UX-1)", () => {
  it("plano incompleto mostra ≈, sem sinal e em tom neutro", () => {
    const g = gainPresentation("1.53", "USD", "incomplete");
    expect(g.text).toBe("≈ US$ 1,53");
    expect(g.tone).toBe("muted");
  });

  it("plano com ganho confirmado mostra sinal e tom de ganho", () => {
    const g = gainPresentation("1.53", "USD", "quoted");
    expect(g.text).toBe("+US$ 1,53");
    expect(g.tone).toBe("gain");
  });

  it("prejuízo sai em tom de perda, mesmo quando é estimado", () => {
    const g = gainPresentation("-4.26", "BRL", "estimated");
    expect(g.tone).toBe("loss");
    expect(g.text).toContain("4,26");
    expect(g.text.startsWith("+")).toBe(false);
  });

  it("lista os custos que faltam pelo nome em português", () => {
    expect(unknownCostLabels({ spread: "1", fees: null, iof: null, transport: "0" })).toEqual(["tarifas", "IOF"]);
    expect(unknownCostLabels(null)).toEqual([]);
  });
});

describe("contagem da cotação (UX-4)", () => {
  it("fala em minutos e segundos, sem parecer hora do dia", () => {
    expect(formatPlanCountdown(900)).toBe("15 min");
    expect(formatPlanCountdown(549)).toBe("9 min 9 s");
    expect(formatPlanCountdown(9)).toBe("9 s");
    expect(formatPlanCountdown(0)).toBe("0 s");
  });
});
