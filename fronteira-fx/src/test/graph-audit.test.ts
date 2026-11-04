import { describe, expect, it } from "vitest";
import { applyEdge, edgesFromQuotes, findCycles, iofApplies } from "@/lib/graph";
import type { Edge, Quote } from "@/lib/api/types";

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

describe("custo desconhecido nunca vira zero no espelho TS (M1, UX-5)", () => {
  it("transferência que converte moeda tem spread null, nunca \"0\"", () => {
    const edges = [
      base({ from: "BRL@brbank", to: "USD@nomad", kind: "transfer", rate: "0.18", confidence: "incomplete" }),
      base({ from: "USD@nomad", to: "BRL@brbank", kind: "transfer", rate: "5.5", confidence: "estimated" }),
    ];
    const c = findCycles(edges, { "BRL@brbank": "1000" }, { maxLen: 2 })[0];
    expect(c.legs[0].costs.spread).toBeNull();
    expect(c.costs?.spread).toBeNull();
  });

  it("transferência na mesma moeda continua com spread zero conhecido", () => {
    const edges = [
      base({ from: "USD@nomad", to: "USD@revolut", kind: "transfer", rate: "1", confidence: "estimated" }),
      base({ from: "USD@revolut", to: "USD@nomad", kind: "transfer", rate: "1", confidence: "estimated" }),
    ];
    const c = findCycles(edges, { "USD@nomad": "100" }, { maxLen: 2 })[0];
    expect(c.legs[0].costs.spread).toBe("0");
  });

  it("conversão de BRL em instituição brasileira tem IOF null (alíquota não conhecida)", () => {
    expect(iofApplies("revolut", "BRL", "USD")).toBe(true);
    expect(iofApplies("nomad", "BRL", "USD")).toBe(true);
    expect(iofApplies("brbank", "BRL", "PYG")).toBe(true);
    expect(iofApplies("chaco:FOZ", "BRL", "USD")).toBe(true);
    expect(iofApplies("chaco:CDE", "BRL", "USD")).toBe(false);
    expect(iofApplies("revolut", "USD", "BRL")).toBe(false); // IOF do lado do BRL que sai
    expect(iofApplies("cash:FOZ", "BRL", "USD")).toBe(false);
    const edges = [
      base({ from: "BRL@revolut", to: "USD@revolut", kind: "quote", rate: "0.18", confidence: "incomplete", ref_rate: "0.1851" }),
      base({ from: "USD@revolut", to: "BRL@revolut", kind: "quote", rate: "5.5", confidence: "estimated", ref_rate: "5.5" }),
    ];
    const c = findCycles(edges, { "BRL@revolut": "1000" }, { maxLen: 2 })[0];
    expect(c.legs[0].costs.iof).toBeNull();
    expect(c.costs?.iof).toBeNull();
    expect(c.confidence).toBe("incomplete");
  });

  it("quote de venda de USD em casa de FOZ com BRL que sai do Brasil já sai com IOF desconhecido", () => {
    const q = {
      source_id: "casa",
      base: "USD",
      quote: "BRL",
      buy: "5.40",
      sell: "5.44",
      kind: "executable",
      modality: "cash",
      channel: "physical",
      city: "FOZ",
      fees: [],
      evidence_id: null,
    } as unknown as Quote;
    const edges = edgesFromQuotes([q], () => "casa:FOZ");
    const venda = edges.find((e) => e.from === "BRL@casa:FOZ" && e.to === "USD@casa:FOZ");
    expect(venda?.confidence).toBe("incomplete");
  });

  it("quote de BRL em casa fora do Brasil segue com IOF zero conhecido", () => {
    const q = {
      source_id: "chaco",
      base: "USD",
      quote: "PYG",
      buy: "7300",
      sell: "7350",
      kind: "executable",
      modality: "cash",
      channel: "physical",
      city: "CDE",
      fees: [],
      evidence_id: null,
    } as unknown as Quote;
    const edges = edgesFromQuotes([q], () => "chaco:CDE");
    expect(edges.every((e) => e.confidence !== "incomplete")).toBe(true);
  });
});

describe("profundidade conta pernas; balcão é grátis (M3)", () => {
  // comprar USD numa casa e vender noutra da mesma cidade: 6 arestas, 2 pernas de câmbio
  const balcao = (from: string, to: string) => base({ from, to, kind: "deposit", rate: "1", minutes: 0, via: "balcão", confidence: "estimated", counter: true });
  const route = (): Edge[] => [
    balcao("BRL@cash:CDE", "BRL@a:CDE"),
    base({ from: "BRL@a:CDE", to: "USD@a:CDE", kind: "quote", rate: "0.18868", channel: "presencial", confidence: "quoted" }),
    balcao("USD@a:CDE", "USD@cash:CDE"),
    balcao("USD@cash:CDE", "USD@b:CDE"),
    base({ from: "USD@b:CDE", to: "BRL@b:CDE", kind: "quote", rate: "5.5", channel: "presencial", confidence: "quoted" }),
    balcao("BRL@b:CDE", "BRL@cash:CDE"),
  ];

  it("a rota com duas trocas e quatro balcões cabe em maxLen 2 (2 pernas)", () => {
    const cycles = findCycles(route(), { "BRL@cash:CDE": "10000" }, { maxLen: 2 });
    expect(cycles.some((c) => c.edges.length === 6 && Number(c.gain) > 0)).toBe(true);
  });

  it("três trocas não cabem em maxLen 2", () => {
    const edges = [
      ...route(),
      base({ from: "BRL@cash:CDE", to: "BRL@c:CDE", kind: "deposit", rate: "1", counter: true, confidence: "estimated" }),
    ];
    const cycles = findCycles(edges, { "BRL@cash:CDE": "10000" }, { maxLen: 2 });
    for (const c of cycles) expect(c.edges.filter((e) => !e.counter).length).toBeLessThanOrEqual(2);
  });
});

describe("aresta publicada reconstrói o montante (M6)", () => {
  it("iof_pct e transport_fixed entram na conta", () => {
    const e = base({ rate: "1", iof_pct: "0.01", transport_fixed: "50" });
    expect(applyEdge(1000, e)).toBeCloseTo(1000 * 0.99 - 50, 8);
  });

  it("deslocamento lê o custo de transport_fixed, não de fee_fixed", () => {
    const edges = [
      base({ from: "BRL@cash:FOZ", to: "BRL@cash:CDE", kind: "travel", rate: "1", transport_fixed: "50", confidence: "estimated", channel: "presencial" }),
      base({ from: "BRL@cash:CDE", to: "BRL@cash:FOZ", kind: "travel", rate: "1", transport_fixed: "50", confidence: "estimated", channel: "presencial" }),
    ];
    const c = findCycles(edges, { "BRL@cash:FOZ": "10000" }, { maxLen: 2 })[0];
    expect(c.amount_out).toBe("9900");
    expect(c.legs[0].costs.transport).toBe("50");
  });
});
