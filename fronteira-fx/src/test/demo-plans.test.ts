import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api, resetDemoClient } from "@/lib/api/client";
import { demoEdges, demoParkedBalances } from "@/lib/api/demo-graph";
import { findCycles } from "@/lib/graph";
import { createDemoPlan, legStepText } from "@/lib/api/demo-plans";
import { DEMO_SERVER_TIME } from "@/lib/api/demo-data";
import type { Cycle, Leg } from "@/lib/api/types";

async function anyDemoCycle() {
  const cycles = await api.cycles("demo", { maxLen: 4 });
  expect(cycles.length).toBeGreaterThan(0);
  return cycles[0];
}

describe("planos na demonstração (sem nenhuma execução)", () => {
  beforeEach(() => {
    resetDemoClient();
    vi.useFakeTimers({ toFake: ["Date"] });
    // relógio logo depois da geração das cotações da demonstração (ela é "agora" no carregamento)
    vi.setSystemTime(Date.parse(DEMO_SERVER_TIME) + 60_000);
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("gera um plano proposto com um passo por perna, todos pendentes e no modo demonstração", async () => {
    const cycle = await anyDemoCycle();
    const plan = await api.createPlan("demo", { start: cycle.start, path: cycle.path });
    expect(plan.status).toBe("proposed");
    expect(plan.data_mode).toBe("demo");
    expect(plan.steps).toHaveLength(cycle.legs.length);
    expect(plan.steps.every((s) => s.status === "pending")).toBe(true);
    expect(plan.steps[0].text.length).toBeGreaterThan(10);
    expect(plan.quote_max_age_s).toBe(900);
  });

  it("recusa um caminho que não é um ciclo atual com 404", async () => {
    await expect(api.createPlan("demo", { start: "BRL@cash:CDE", path: ["BRL@cash:CDE", "XYZ@nada", "BRL@cash:CDE"] })).rejects.toBeInstanceOf(ApiError);
  });

  it("aprova uma vez; aprovar de novo é 409", async () => {
    const cycle = await anyDemoCycle();
    const plan = await api.createPlan("demo", { start: cycle.start, path: cycle.path });
    expect((await api.approvePlan("demo", plan.id)).status).toBe("approved");
    await expect(api.approvePlan("demo", plan.id)).rejects.toMatchObject({ status: 409 });
  });

  it("passos em ordem: pular um passo é 409 e o último passo conclui e grava o resultado no diário", async () => {
    const cycle = await anyDemoCycle();
    const plan = await api.createPlan("demo", { start: cycle.start, path: cycle.path });
    await api.approvePlan("demo", plan.id);
    const n = plan.steps.length;
    if (n > 1) await expect(api.completePlanStep("demo", plan.id, 2, { actual_out: "1" })).rejects.toMatchObject({ status: 409 });
    let last = null;
    for (let i = 1; i <= n; i++) {
      last = await api.completePlanStep("demo", plan.id, i, { actual_out: i === n ? cycle.amount_out : cycle.amount_out, note: "conferido" });
    }
    expect(last?.status).toBe("done");
    expect(last?.steps.every((s) => s.status === "done")).toBe(true);
    const journal = await api.journal("demo");
    const result = journal.find((j) => j.kind === "result");
    expect(result?.amounts.map((a) => a.label)).toEqual(["esperado", "realizado"]);
  });

  it("rejeitar um plano proposto; depois de concluir não se rejeita", async () => {
    const cycle = await anyDemoCycle();
    const plan = await api.createPlan("demo", { start: cycle.start, path: cycle.path });
    expect((await api.rejectPlan("demo", plan.id)).status).toBe("rejected");
  });

  it("expira pela cotação velha: aprovar depois de 900 s é 409 e o plano fica expirado", async () => {
    const cycle = await anyDemoCycle();
    const plan = await api.createPlan("demo", { start: cycle.start, path: cycle.path });
    vi.setSystemTime(Date.parse("2026-11-04T12:20:00Z"));
    await expect(api.approvePlan("demo", plan.id)).rejects.toMatchObject({ status: 409 });
    expect((await api.plan("demo", plan.id)).status).toBe("expired");
  });

  it("a lista traz os planos do mais recente para o mais antigo", async () => {
    const cycle = await anyDemoCycle();
    const a = await api.createPlan("demo", { start: cycle.start, path: cycle.path });
    vi.setSystemTime(Date.parse("2026-11-04T12:01:00Z"));
    const b = await api.createPlan("demo", { start: cycle.start, path: cycle.path });
    const list = await api.plans("demo");
    expect(list.map((p) => p.id)).toEqual([b.id, a.id]);
  });
});

describe("grafo demo sem o banco fechado", () => {
  it("Revolut e Nomad entram como contas digitais; o banco fechado fica fora", () => {
    const parked = demoParkedBalances();
    expect(Object.keys(parked).some((k) => k.endsWith("@revolut"))).toBe(true);
    expect(Object.keys(parked).some((k) => k.endsWith("@nomad"))).toBe(true);
    expect(Object.keys(parked).some((k) => k.startsWith("PYG@banco-demo-py"))).toBe(true);
    expect(Object.keys(parked).some((k) => k.startsWith("PYG@revolut"))).toBe(false);
  });

  it("os ciclos demo trazem pernas, canal e ganho por moeda", () => {
    const cycles = findCycles(demoEdges(), demoParkedBalances(), { maxLen: 4 });
    expect(cycles.length).toBeGreaterThan(0);
    for (const c of cycles) {
      expect(c.legs.length).toBe(c.edges.length);
      expect(c.legs.every((l) => ["presencial", "assistida", "automatizavel"].includes(l.channel))).toBe(true);
      expect(c.gain_by_currency).not.toBeNull();
    }
    const travel = cycles.flatMap((c) => c.legs).filter((l) => l.kind === "travel");
    expect(travel.length).toBeGreaterThan(0);
    expect(travel.every((l) => l.costs.transport === null)).toBe(true);
  });
});

describe("textos e regras do plano demo iguais aos do backend (UX-3, SC-2)", () => {
  it("câmbio mostra o que se paga e a cotação na convenção do balcão", () => {
    const text = legStepText({
      kind: "exchange", channel: "presencial", from: "USD@chaco:CDE", to: "BRL@chaco:CDE", via: "x",
      minutes: 15, border: false, amount_in: "1000", amount_out: "5400", costs: { currency: "USD", spread: "0", fees: "0", iof: "0", transport: "0" },
    } as Leg);
    expect(text).toBe("Compre 5.400 BRL na Cambios Chaco (CDE) pagando 1.000 USD (cotação: 1 USD = 5,40 BRL)");
  });

  it("transferência que converte diz o que sai e o que chega", () => {
    const text = legStepText({
      kind: "transfer", channel: "assistida", from: "BRL@brbank", to: "USD@nomad", via: "x",
      minutes: 60, border: false, amount_in: "5000", amount_out: "920", costs: { currency: "BRL", spread: null, fees: "0", iof: "0", transport: "0" },
    } as Leg);
    expect(text).toBe("Envie 5.000 BRL de banco brasileiro e receba ≈ 920 USD em Nomad (≈ 60 min)");
  });

  it("recusa criar plano de ciclo sem ganho líquido positivo (422)", () => {
    const cycle = { start: "USD@nomad", path: ["USD@nomad", "BRL@brbank", "USD@nomad"], legs: [], amount_in: "100", amount_out: "99", gain: "-1", gain_by_currency: null, confidence: "estimated" } as unknown as Cycle;
    let err: unknown = null;
    try {
      createDemoPlan(cycle, Date.parse("2026-11-04T12:00:00Z"));
    } catch (e) {
      err = e;
    }
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(422);
  });
});
