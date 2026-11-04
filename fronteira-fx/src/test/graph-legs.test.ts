import { describe, expect, it } from "vitest";
import { findCycles } from "@/lib/graph";
import type { Edge } from "@/lib/api/types";

const base = (over: Partial<Edge>): Edge => ({
  from: "BRL@a",
  to: "USD@b",
  kind: "transfer",
  rate: "0.2",
  fee_pct: "0",
  fee_fixed: "0",
  minutes: 10,
  via: "via",
  confidence: "quoted",
  evidence_id: null,
  channel: "assistida",
  ...over,
});

// Ciclo BRL@a → USD@b → BRL@a: 1000 BRL viram 198 USD (1 % de tarifa) e voltam a 1089 BRL.
const out = (e1: Partial<Edge>, e2: Partial<Edge>, capital = "1000") => {
  const edges = [base(e1), base({ from: "USD@b", to: "BRL@a", rate: "5.5", channel: "presencial", ...e2 })];
  return findCycles(edges, { "BRL@a": capital }, { maxLen: 2 })[0];
};

describe("pernas do ciclo (contrato: legs[])", () => {
  it("cada aresta vira uma perna com tipo, canal e custos na moeda de origem", () => {
    const c = out({ fee_pct: "0.01" }, {});
    expect(c.legs).toHaveLength(2);
    expect(c.legs[0]).toMatchObject({ kind: "transfer", channel: "assistida", from: "BRL@a", to: "USD@b", border: false });
    expect(c.legs[0].costs.currency).toBe("BRL");
    expect(Number(c.legs[0].costs.fees)).toBeCloseTo(10, 6);
    expect(c.legs[1].channel).toBe("presencial");
  });

  it("spread é calculado só com taxa de referência; sem ela é desconhecido (null), nunca zero", () => {
    const sem = out({ kind: "quote" }, {});
    expect(sem.legs[0].kind).toBe("exchange");
    expect(sem.legs[0].costs.spread).toBeNull();
    expect(sem.costs?.spread).toBeNull();
    const com = out({ kind: "quote", ref_rate: "0.2002" }, {});
    expect(Number(com.legs[0].costs.spread)).toBeCloseTo(0.999, 2);
  });

  it("deslocamento com custo desconhecido: transporte null e confiança incompleta", () => {
    const c = out({ kind: "travel", channel: "presencial", confidence: "incomplete", rate: "1", via: "ônibus CDE → ASU" }, {});
    expect(c.legs[0]).toMatchObject({ kind: "travel", channel: "presencial" });
    expect(c.legs[0].costs.transport).toBeNull();
    expect(c.costs?.transport).toBeNull();
    expect(c.confidence).toBe("incomplete");
  });

  it("perna que cruza a fronteira marca border e pede declaração acima de US$ 10 000", () => {
    const pequeno = out({}, { border: true });
    expect(pequeno.legs[1].border).toBe(true);
    expect(pequeno.requires_declaration).toBe(false);
    const grande = out({}, { border: true }, "100000");
    expect(grande.requires_declaration).toBe(true);
  });

  it("ganho líquido em BRL, USD e PYG a partir das taxas de valoração", () => {
    const c = out({}, {});
    expect(c.gain).toBe(c.gain_by_currency?.BRL);
    expect(Number(c.gain_by_currency?.BRL)).toBeCloseTo(100, 6); // 1000 → 200 USD → 1100 BRL, sem tarifa
    expect(Number(c.gain_by_currency?.USD)).toBeGreaterThan(0);
    expect(Number(c.gain_by_currency?.PYG)).toBeGreaterThan(Number(c.gain_by_currency?.USD));
  });

  it("custos do ciclo somam na moeda de partida (fees) e a categoria fica null se alguma perna não tem o valor", () => {
    const c = out({ fee_pct: "0.01" }, { fee_pct: "0.02" });
    // 10 BRL na primeira perna + 3,96 USD da segunda (= 20 BRL pela proporção do ciclo)
    expect(Number(c.costs?.fees)).toBeCloseTo(30, 6);
    expect(c.costs?.iof).toBe("0");
  });
});
