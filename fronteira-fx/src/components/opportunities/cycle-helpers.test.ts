import { describe, expect, it } from "vitest";
import type { Cycle } from "@/lib/api/types";
import { costRows, cycleGain, filterCycles, legLabel, legText, cycleCurrency, formatMinutes, isProfitable, NEEDS_DECLARATION_USD, pathLabel, parseMinGain, planButtonLabel, profitBadge } from "./cycle-helpers";

const cycle = (over: Partial<Cycle> = {}): Cycle => ({
  start: "BRL@brbank",
  path: ["BRL@brbank", "USD@nomad", "BRL@brbank"],
  edges: [],
  legs: [
    { kind: "transfer", channel: "assistida", from: "BRL@brbank", to: "USD@nomad", via: "Pix → Nomad", minutes: 1440, border: false, amount_in: "5000", amount_out: "920", costs: { currency: "BRL", spread: null, fees: "0", iof: "0", transport: "0" } },
    { kind: "transfer", channel: "assistida", from: "USD@nomad", to: "BRL@brbank", via: "Nomad → Pix", minutes: 1440, border: false, amount_in: "920", amount_out: "5042", costs: { currency: "USD", spread: null, fees: "0", iof: "0", transport: "0" } },
  ],
  amount_in: "5000",
  amount_out: "5042.10",
  gain: "42.10",
  roi: "0.00842",
  gain_by_currency: { BRL: "42.10", USD: "7.80", PYG: "46000" },
  costs: { spread: null, fees: "0", iof: "0", transport: "0" },
  requires_declaration: false,
  minutes: 2880,
  confidence: "estimated",
  data_mode: "demo",
  ...over,
});

describe("cycle-helpers (ganho, filtros e textos das pernas)", () => {
  it("lê o ganho em qualquer moeda; null quando a conversão falta", () => {
    expect(cycleGain(cycle(), "USD")).toBe(7.8);
    expect(cycleGain(cycle({ gain_by_currency: { BRL: "42.10", USD: null, PYG: null } }), "PYG")).toBeNull();
    expect(cycleGain(cycle({ gain_by_currency: null }), "BRL")).toBe(42.1);
  });

  it("lucrativo = ganho na moeda de partida > 0", () => {
    expect(isProfitable(cycle())).toBe(true);
    expect(isProfitable(cycle({ gain: "-3" }))).toBe(false);
  });

  it("filtro: moeda de partida, ganho mínimo na moeda escolhida e incluir incompletos", () => {
    const ok = cycle();
    const incompleto = cycle({ start: "USD@nomad", confidence: "incomplete" });
    const semConversao = cycle({ start: "PYG@banco_py", gain_by_currency: { BRL: null, USD: null, PYG: null } });
    const list = [ok, incompleto, semConversao];
    expect(filterCycles(list, { currency: "all", minGain: "", minCurrency: "BRL", includeIncomplete: true })).toHaveLength(3);
    expect(filterCycles(list, { currency: "all", minGain: "", minCurrency: "BRL", includeIncomplete: false })).toEqual([ok, semConversao]);
    expect(filterCycles(list, { currency: "USD", minGain: "", minCurrency: "BRL", includeIncomplete: true })).toEqual([incompleto]);
    // ganho mínimo com conversão desconhecida: não há como provar que passa, então sai da lista
    expect(filterCycles(list, { currency: "all", minGain: "10", minCurrency: "PYG", includeIncomplete: true })).toEqual([ok, incompleto]);
    expect(filterCycles(list, { currency: "all", minGain: "50", minCurrency: "BRL", includeIncomplete: true })).toEqual([]);
  });

  it("texto da perna: tipo e destino em português simples, sem nó técnico", () => {
    expect(legLabel("exchange", "presencial")).toBe("Troca presencial");
    expect(legLabel("travel", "presencial")).toBe("Deslocamento");
    expect(legLabel("transfer", "automatizavel")).toBe("Transferência automatizável");
    expect(legText(cycle().legs[0])).toContain("Pix → Nomad");
    expect(legText(cycle().legs[0])).toContain("5.000");
  });

  it("linhas de custo: custo desconhecido aparece como não informado, nunca como zero", () => {
    const rows = costRows(cycle({ costs: { spread: null, fees: "9.9", iof: null, transport: "0" } }), "BRL");
    expect(rows.map((r) => r.label)).toEqual(["Spread", "Tarifas", "IOF", "Deslocamento"]);
    expect(rows[0].value).toBeNull();
    expect(rows[1].value).toBe("R$ 9,90");
    expect(rows[2].value).toBeNull();
    expect(costRows(cycle({ costs: null }), "BRL").every((r) => r.value === null)).toBe(true);
  });

  it("limite de declaração é US$ 10 000 e tempo sai em minutos ou dias", () => {
    expect(NEEDS_DECLARATION_USD).toBe(10000);
    expect(formatMinutes(40)).toBe("40 min");
    expect(formatMinutes(2880)).toBe("2,0 d");
    expect(cycleCurrency("PYG@chaco:CDE")).toBe("PYG");
  });
});

describe("pathLabel", () => {
  it("troca o @ por um separador legível, sem perder a seta", () => {
    expect(pathLabel(["BRL@brbank", "USD@nomad", "BRL@brbank"])).toBe("BRL · brbank → USD · nomad → BRL · brbank");
  });
});

describe("ganho mínimo lê o número como o resto do app (UX-2)", () => {
  it("aceita pt-BR com separador de milhar e vírgula decimal", () => {
    expect(parseMinGain("10.000")).toEqual({ ok: true, value: 10000 });
    expect(parseMinGain("20,5")).toEqual({ ok: true, value: 20.5 });
    expect(parseMinGain("1.250,50")).toEqual({ ok: true, value: 1250.5 });
    expect(parseMinGain("")).toEqual({ ok: true, value: null });
  });

  it("entrada ilegível não deixa passar ciclo nenhum e é sinalizada", () => {
    expect(filterCycles([cycle()], { currency: "all", minGain: "abc", minCurrency: "BRL", includeIncomplete: true })).toEqual([]);
    expect(parseMinGain("abc")).toEqual({ ok: false, value: null });
    expect(parseMinGain("20,5,5")).toEqual({ ok: false, value: null });
    expect(parseMinGain("20.5")).toEqual({ ok: true, value: 20.5 }); // ponto com uma casa é decimal, como no alerta
  });

  it("10.000 em guarani deixa de deixar passar ₲ 9.107", () => {
    const list = [
      { start: "PYG@cash:CDE", gain: "9107", gain_by_currency: { BRL: "1", USD: "1", PYG: "9107" }, confidence: "quoted" },
      { start: "PYG@cash:CDE", gain: "12000", gain_by_currency: { BRL: "1", USD: "1", PYG: "12000" }, confidence: "quoted" },
    ] as unknown as Cycle[];
    expect(filterCycles(list, { currency: "all", minGain: "10.000", minCurrency: "PYG", includeIncomplete: true })).toHaveLength(1);
  });
});

describe("cruzamento: contagem de lucrativos e rótulo do plano (custo pendente nunca é confirmado)", () => {
  it("sem nenhum ciclo positivo, o selo é neutro: 0 lucrativos", () => {
    expect(profitBadge([])).toEqual({ text: "0 lucrativos", variant: "outline" });
  });

  it("só ciclo com custo pendente: nada confirmado, selo neutro, com a contagem da estimativa", () => {
    const badge = profitBadge([cycle({ confidence: "incomplete" }), cycle({ confidence: "incomplete" })]);
    expect(badge.text).toBe("0 confirmados · 2 estimados (custo pendente)");
    expect(badge.variant).toBe("outline");
  });

  it("confirmados e estimados contados em separado; o verde só aparece com confirmado", () => {
    const badge = profitBadge([cycle({ confidence: "quoted" }), cycle({ confidence: "incomplete" })]);
    expect(badge).toEqual({ text: "1 confirmado · 1 estimado (custo pendente)", variant: "gain" });
  });

  it("ciclo sem ganho não entra na contagem", () => {
    expect(profitBadge([cycle({ gain: "-3", confidence: "quoted" })]).text).toBe("0 lucrativos");
  });

  it("o botão de um ciclo com custo pendente diz que é estimativa", () => {
    expect(planButtonLabel(cycle({ confidence: "incomplete" }))).toBe("Gerar plano (estimativa)");
    expect(planButtonLabel(cycle({ confidence: "quoted" }))).toBe("Gerar plano");
  });
});
