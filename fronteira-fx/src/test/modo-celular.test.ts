import { describe, expect, it } from "vitest";
import { api } from "@/lib/api/client";
import { isCelularEdge } from "@/lib/graph";
import type { Edge } from "@/lib/api/types";

function edge(over: Partial<Edge>): Edge {
  return {
    from: "BRL@brbank", to: "PYG@banco-demo-py", kind: "transfer", rate: "1400", fee_pct: "0", fee_fixed: "0",
    minutes: 60, via: "", confidence: "estimated", evidence_id: null, channel: "assistida", ...over,
  };
}

describe("modo celular (regra do dono)", () => {
  it("só assistida ou automatizável entra; deposito, saque, deslocamento e balcão ficam de fora", () => {
    expect(isCelularEdge(edge({}))).toBe(true);
    expect(isCelularEdge(edge({ channel: "automatizavel" }))).toBe(true);
    expect(isCelularEdge(edge({ channel: "presencial" }))).toBe(false);
    expect(isCelularEdge(edge({ kind: "deposit" }))).toBe(false);
    expect(isCelularEdge(edge({ kind: "withdraw" }))).toBe(false);
    expect(isCelularEdge(edge({ kind: "travel" }))).toBe(false);
    expect(isCelularEdge(edge({ counter: true }))).toBe(false);
  });

  it("ranking de oportunidades padrão: nenhuma rota presencial; modo todos inclui o presencial", async () => {
    const celular = await api.opportunities("demo", {});
    expect(celular.length).toBeGreaterThan(0);
    expect(celular.every((o) => o.channel !== "physical")).toBe(true);
    const todos = await api.opportunities("demo", { mode: "todos" });
    expect(todos.some((o) => o.channel === "physical")).toBe(true);
  });

  it("ciclos padrão: nenhuma perna presencial; modo todos traz ciclo com perna presencial", async () => {
    const celular = await api.cycles("demo", { maxLen: 4 });
    expect(celular.every((c) => c.legs.every((l) => l.channel !== "presencial"))).toBe(true);
    const todos = await api.cycles("demo", { maxLen: 4, mode: "todos" });
    expect(todos.some((c) => c.legs.some((l) => l.channel === "presencial"))).toBe(true);
  });
});
