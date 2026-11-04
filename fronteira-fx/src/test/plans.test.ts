import { describe, expect, it } from "vitest";
import { applyPlanClock, canApprove, canCompleteStep, canReject, nextPendingStep, resultOf } from "@/lib/plans";
import type { Plan } from "@/lib/api/types";

const T0 = Date.parse("2026-11-04T12:00:00Z");
const plan = (over: Partial<Plan> = {}): Plan => ({
  id: "p1",
  status: "proposed",
  start: "BRL@cash:CDE",
  path: ["BRL@cash:CDE", "PYG@chaco:CDE", "BRL@cash:CDE"],
  currency: "BRL",
  amount_in: "5000",
  amount_out_expected: "5100",
  gain_expected: "100",
  gain_by_currency: { BRL: "100", USD: "18.5", PYG: "109999" },
  confidence: "quoted",
  minutes: 40,
  requires_declaration: false,
  quotes_as_of: new Date(T0).toISOString(),
  quote_max_age_s: 900,
  created_at: new Date(T0).toISOString(),
  decided_at: null,
  completed_at: null,
  data_mode: "demo",
  steps: [
    { n: 1, kind: "exchange", channel: "presencial", text: "Troque", from: "BRL@cash:CDE", to: "PYG@chaco:CDE", amount_in: "5000", amount_out_expected: "5560000", minutes: 0, status: "pending", actual_out: null, note: null, done_at: null },
    { n: 2, kind: "exchange", channel: "presencial", text: "Troque", from: "PYG@chaco:CDE", to: "BRL@cash:CDE", amount_in: "5560000", amount_out_expected: "5100", minutes: 0, status: "pending", actual_out: null, note: null, done_at: null },
  ],
  ...over,
});

describe("relógio do plano: expira pela cotação mais velha, só antes do primeiro passo", () => {
  it("antes de 900 s a proposta segue viva", () => {
    expect(applyPlanClock(plan(), T0 + 899_000).status).toBe("proposed");
  });
  it("depois de 900 s a proposta vira expired", () => {
    expect(applyPlanClock(plan(), T0 + 900_000).status).toBe("expired");
  });
  it("aprovado e ainda sem passo feito também expira", () => {
    expect(applyPlanClock(plan({ status: "approved" }), T0 + 901_000).status).toBe("expired");
  });
  it("depois do primeiro passo não expira mais", () => {
    expect(applyPlanClock(plan({ status: "in_progress" }), T0 + 9_000_000).status).toBe("in_progress");
  });
});

describe("transições permitidas na interface (espelham o backend)", () => {
  it("aprovar só quando proposto e vivo", () => {
    expect(canApprove(plan(), T0)).toBe(true);
    expect(canApprove(plan({ status: "approved" }), T0)).toBe(false);
    expect(canApprove(plan(), T0 + 901_000)).toBe(false);
  });
  it("rejeitar em proposed ou approved, nunca depois de um passo", () => {
    expect(canReject(plan(), T0)).toBe(true);
    expect(canReject(plan({ status: "approved" }), T0)).toBe(true);
    expect(canReject(plan({ status: "in_progress" }), T0)).toBe(false);
  });
  it("passos em ordem: só o próximo pendente, e só com o plano aprovado", () => {
    const aprovado = plan({ status: "approved" });
    expect(nextPendingStep(aprovado)?.n).toBe(1);
    expect(canCompleteStep(aprovado, 1, T0)).toBe(true);
    expect(canCompleteStep(aprovado, 2, T0)).toBe(false);
    expect(canCompleteStep(plan(), 1, T0)).toBe(false);
  });
});

describe("resultado: esperado × realizado", () => {
  it("só existe com o plano concluído, e a diferença é realizado − esperado", () => {
    expect(resultOf(plan())).toBeNull();
    const done = plan({
      status: "done",
      steps: [
        { ...plan().steps[0], status: "done", actual_out: "5560000" },
        { ...plan().steps[1], status: "done", actual_out: "5090" },
      ],
    });
    const r = resultOf(done);
    expect(r).toMatchObject({ expected: "5100", realized: "5090", difference: "-10" });
  });
});
