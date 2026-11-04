import { describe, expect, it } from "vitest";
import { ApiError, api, resetDemoClient } from "@/lib/api/client";
import { demoEdges, demoTransferEdges } from "@/lib/api/demo-graph";
import { createDemoPlan } from "@/lib/api/demo-plans";
import { findCycles, iofApplies } from "@/lib/graph";
import type { Cycle } from "@/lib/api/types";

// Revisão do espelho TS: mesmas regras de IOF, custo desconhecido e validade de plano do backend.

describe("IOF no espelho (mesma regra do backend: fora do lado paraguaio, IOF desconhecido)", () => {
  it.each([
    ["wu", "BRL", "PYG", true],
    ["demo-nomad", "BRL", "USD", true],
    ["brbank", "BRL", "USD", true],
    ["casa:FOZ", "BRL", "USD", true],
    ["chaco:CDE", "BRL", "PYG", false],
    ["cash:CDE", "BRL", "USD", false],
    ["banco_py", "BRL", "PYG", false],
    ["chaco", "BRL", "PYG", false],
    ["chaco:CDE", "USD", "BRL", false],
  ] as const)("%s %s→%s: %s", (venue, from, to, expected) => {
    expect(iofApplies(venue, from, to)).toBe(expected);
  });
});

describe("saque e depósito do Banco PY: custo não verificado, nunca zero", () => {
  it("todas as arestas de saque e depósito do Banco PY são incompletas e sem tarifa conhecida", () => {
    const bank = demoTransferEdges().filter((e) => /^(saque|depósito) Banco PY/.test(e.via));
    expect(bank.length).toBeGreaterThan(0);
    for (const e of bank) {
      expect(e.confidence).toBe("incomplete");
      expect(e.unknown_costs).toContain("fees");
    }
  });

  it("o ciclo PYG@banco_py → PYG@cash:ASU → PYG@banco_py não aparece como estimativa com custo zero", () => {
    const cycles = findCycles(demoEdges(), { "PYG@banco_py": "1000000" }, { maxLen: 4 });
    const loop = cycles.filter((c) => c.path.length === 3 && c.path.includes("PYG@cash:ASU"));
    expect(loop.length).toBeGreaterThan(0);
    for (const c of loop) {
      expect(c.confidence).toBe("incomplete");
      expect(c.costs?.fees).toBeNull();
    }
  });
});

describe("validade do plano na demonstração", () => {
  const T0 = Date.parse("2026-11-04T12:00:00Z");
  const cycle = (over: Partial<Cycle> = {}): Cycle =>
    ({
      start: "PYG@cash:CDE",
      path: ["PYG@cash:CDE", "PYG@chaco:CDE", "USD@chaco:CDE", "USD@cash:CDE"],
      edges: [
        { from: "PYG@cash:CDE", to: "PYG@chaco:CDE", kind: "quote", rate: "0.00013", fee_pct: "0", fee_fixed: "0", minutes: 0, via: "a", confidence: "quoted", evidence_id: null, channel: "presencial", quoted_at: "2026-11-01T12:00:00.000Z" },
        { from: "PYG@chaco:CDE", to: "USD@chaco:CDE", kind: "quote", rate: "0.0001", fee_pct: "0", fee_fixed: "0", minutes: 0, via: "b", confidence: "quoted", evidence_id: null, channel: "presencial", quoted_at: "2026-11-04T11:59:00.000Z" },
      ],
      legs: [],
      amount_in: "7300000",
      amount_out: "7400000",
      gain: "100000",
      roi: "0.0137",
      gain_by_currency: { BRL: "70", USD: "13.7", PYG: "100000" },
      costs: { spread: "0", fees: "0", iof: "0", transport: "0" },
      requires_declaration: false,
      minutes: 55,
      confidence: "quoted",
      data_mode: "demo",
      ...over,
    }) as Cycle;

  it("a data do plano é a cotação mais velha do ciclo, não o instante da criação", () => {
    const plan = createDemoPlan(cycle(), T0);
    expect(plan.quotes_as_of).toBe("2026-11-01T12:00:00.000Z");
    expect(plan.created_at).toBe(new Date(T0).toISOString());
  });

  it("ciclo sem nenhuma data de cotação não vira plano (422)", () => {
    const edges = cycle().edges.map((e) => ({ ...e, quoted_at: null }));
    expect(() => createDemoPlan(cycle({ edges }), T0)).toThrow(ApiError);
  });

  it("caminho com mais de 21 nós é recusado como no backend (422)", async () => {
    resetDemoClient();
    const path = Array.from({ length: 22 }, (_, i) => (i % 2 === 0 ? "BRL@cash:CDE" : "USD@chaco:CDE"));
    await expect(api.createPlan("demo", { start: "BRL@cash:CDE", path })).rejects.toMatchObject({ status: 422 });
  });
});
