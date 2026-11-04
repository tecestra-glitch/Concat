import { describe, expect, it } from "vitest";
import type { Quote, Source } from "@/lib/api/types";
import { demoSources, seriesKey } from "@/lib/api/demo-data";
import { demoQuotesAt, demoSessions } from "@/lib/pregao/demo";
import { defaultKeyFor, refMidFor } from "@/lib/pregao/derive";
import type { HouseSession } from "@/lib/pregao/types";
import { buildPregaoView, cyclePair } from "@/lib/pregao/view";

const NOW = new Date(Date.UTC(2026, 10, 2, 12, 0)); // segunda, 09:00 em Assunção: casas abertas
const ago = (s: number) => new Date(NOW.getTime() - s * 1000).toISOString();

function mkQuote(p: Partial<Quote> & Pick<Quote, "id" | "source_id">): Quote {
  const q: Omit<Quote, "series_key"> = {
    branch_id: null,
    city: "CDE",
    base: "USD",
    quote: "PYG",
    buy: "5905",
    sell: "5975",
    unit_note: "PYG por 1 USD",
    amount_base: null,
    modality: "cash",
    kind: "indicative",
    channel: "physical",
    context: null,
    fees: [],
    captured_at: ago(120),
    declared_updated_at: null,
    valid_until: null,
    evidence_id: `ev-${p.id}`,
    data_mode: "real",
    ...p,
  };
  return { ...q, series_key: p.series_key ?? seriesKey(q) };
}

const src = (id: string, name: string, kind: Source["kind"] = "exchange_house"): Source => ({
  id,
  name,
  kind,
  method: "html",
  integration: "html",
  url: "",
  health: "ok",
  last_success_at: null,
  last_error: null,
  capabilities: [],
  limitations: [],
  coverage: { cities: [], currencies: ["USD", "PYG", "BRL"] },
  poll_interval_s: 300,
  data_mode: "real",
});

const demo = () => ({ quotes: demoQuotesAt(NOW), sources: demoSources, sessions: demoSessions(NOW), now: NOW });

describe("buildPregaoView — série escolhida", () => {
  it("sem seleção usa a primeira casa aberta do par (nunca a referência)", () => {
    const v = buildPregaoView({ ...demo(), pair: "USD/PYG", selectedKey: null });
    expect(v.levels.length).toBeGreaterThan(0);
    expect(v.levels.every((l) => l.pair === "USD/PYG")).toBe(true);
    expect(v.effectiveKey).toBe(defaultKeyFor(v.levels));
    expect(v.selectedLevel?.key).toBe(v.effectiveKey);
    expect(v.selectedLevel?.kind).not.toBe("market_reference");
  });

  it("seleção válida no par vence; chave de outro par ou desconhecida cai no padrão", () => {
    const base = buildPregaoView({ ...demo(), pair: "USD/PYG", selectedKey: null });
    const other = base.levels.find((l) => l.kind !== "market_reference" && l.key !== base.effectiveKey);
    expect(other).toBeDefined();
    expect(buildPregaoView({ ...demo(), pair: "USD/PYG", selectedKey: other!.key }).effectiveKey).toBe(other!.key);
    const brlKey = base.levelsByPair["BRL/PYG"][0].key;
    expect(buildPregaoView({ ...demo(), pair: "USD/PYG", selectedKey: brlKey }).effectiveKey).toBe(base.effectiveKey);
    expect(buildPregaoView({ ...demo(), pair: "USD/PYG", selectedKey: "nada:CDE:USD/PYG:cash" }).effectiveKey).toBe(base.effectiveKey);
  });

  it("par sem cotações: nada selecionado, sem série", () => {
    const v = buildPregaoView({ quotes: [], sources: [], sessions: [], pair: "USD/BRL", selectedKey: null, now: NOW });
    expect(v.levels).toEqual([]);
    expect(v.effectiveKey).toBeNull();
    expect(v.selectedLevel).toBeNull();
    expect(v.allKeys).toEqual([]);
    expect(v.reference).toBeNull();
    expect(v.cross).toEqual({ house: "—", usdPyg: null, usdBrl: null, direct: null });
  });
});

describe("buildPregaoView — chaves, mapa de calor e referência", () => {
  it("levelsByPair cobre os 3 pares; allKeys são únicas e incluem a referência (resumo da fita)", () => {
    const v = buildPregaoView({ ...demo(), pair: "USD/PYG", selectedKey: null });
    expect(Object.keys(v.levelsByPair)).toEqual(["USD/PYG", "BRL/PYG", "USD/BRL"]);
    expect(new Set(v.allKeys).size).toBe(v.allKeys.length);
    expect(v.allKeys.length).toBe(v.allLevels.length);
    expect(v.allLevels.some((l) => l.kind === "market_reference" && v.allKeys.includes(l.key))).toBe(true);
  });

  it("houseKeys (miniaturas da lista) são só as casas do par atual", () => {
    const v = buildPregaoView({ ...demo(), pair: "BRL/PYG", selectedKey: null });
    expect(v.houseKeys.length).toBeGreaterThan(0);
    expect(v.houseKeys).toEqual(v.levels.filter((l) => l.kind !== "market_reference").map((l) => l.key));
  });

  it("heatHouses: casas únicas na sequência em que aparecem, sem referência", () => {
    const v = buildPregaoView({ ...demo(), pair: "USD/PYG", selectedKey: null });
    const ids = v.heatHouses.map((h) => h.source_id);
    expect(new Set(ids).size).toBe(ids.length);
    expect(ids).not.toContain("bcp");
    expect(ids).toContain("nomad"); // só publica USD/BRL e entra mesmo com o par USD/PYG selecionado
    const firstSeen = [...new Set(v.allLevels.filter((l) => l.kind !== "market_reference").map((l) => l.source_id))];
    expect(ids).toEqual(firstSeen);
    expect(v.heatHouses.find((h) => h.source_id === "chaco")?.house).toBe("Cambios Chaco");
  });

  it("referência do gráfico: mid do BCP, rótulo com o nome da fonte e prefixo ≈", () => {
    const d = demo();
    const v = buildPregaoView({ ...d, pair: "USD/PYG", selectedKey: null });
    expect(v.reference).toEqual({ value: String(refMidFor(d.quotes, "USD/PYG", NOW)), label: "≈ BCP (referência)" });
  });

  it("rótulo e valor vêm da mesma referência (empate de prioridade: vale a mais recente)", () => {
    const refA = mkQuote({ id: "ra", source_id: "ref-a", city: null, kind: "market_reference", channel: "digital", modality: "transfer", buy: "5900", sell: "5900", captured_at: ago(600) });
    const refB = mkQuote({ id: "rb", source_id: "ref-b", city: null, kind: "market_reference", channel: "digital", modality: "transfer", buy: "5950", sell: "5950", captured_at: ago(60) });
    const v = buildPregaoView({ quotes: [refA, refB], sources: [src("ref-a", "Ref A", "central_bank"), src("ref-b", "Ref B", "central_bank")], sessions: [], pair: "USD/PYG", selectedKey: null, now: NOW });
    expect(v.reference).toEqual({ value: "5950", label: "≈ Ref B" });
  });

  it("sem referência recente (24 h) não há linha de referência", () => {
    const quotes = [
      mkQuote({ id: "c", source_id: "chaco" }),
      mkQuote({ id: "r", source_id: "bcp", city: null, kind: "market_reference", channel: "digital", modality: "transfer", buy: "5944.76", sell: "5944.76", captured_at: ago(25 * 3600) }),
    ];
    const v = buildPregaoView({ quotes, sources: [src("chaco", "Cambios Chaco"), src("bcp", "BCP", "central_bank")], sessions: [], pair: "USD/PYG", selectedKey: null, now: NOW });
    expect(v.reference).toBeNull();
  });

  it("referenceNext: próxima mudança da sessão do BCP (com ou sem prefixo demo-)", () => {
    const d = demo();
    const v = buildPregaoView({ ...d, pair: "USD/PYG", selectedKey: null });
    expect(v.referenceNext).toBe(d.sessions.find((s) => s.source_id === "demo-bcp")?.next_change_at ?? null);
    const real: HouseSession[] = [{ source_id: "bcp", name: "BCP", city: null, tz: "America/Asuncion", channel: "digital", reference: true, status: "open", opens_at: null, closes_at: null, next_change_at: "2026-11-02T20:00:00Z", data_mode: "real" }];
    expect(buildPregaoView({ quotes: [], sources: [], sessions: real, pair: "USD/PYG", selectedKey: null, now: NOW }).referenceNext).toBe("2026-11-02T20:00:00Z");
  });
});

describe("buildPregaoView — cruzamento BRL/PYG via USD (mesma casa, mesmo contexto)", () => {
  const sources = [src("chaco", "Cambios Chaco"), src("bcp", "BCP (referência)", "central_bank")];
  const usdPyg = mkQuote({ id: "py", source_id: "chaco", buy: "5905", sell: "5975" });
  const usdBrl = mkQuote({ id: "br", source_id: "chaco", base: "USD", quote: "BRL", buy: "5.40", sell: "5.46", unit_note: "BRL por 1 USD" });
  const brlPyg = mkQuote({ id: "bp", source_id: "chaco", base: "BRL", quote: "PYG", buy: "1092", sell: "1112", unit_note: "PYG por 1 BRL" });
  const bcpRef = mkQuote({ id: "ref", source_id: "bcp", city: null, kind: "market_reference", channel: "digital", modality: "transfer", buy: "5944.76", sell: "5944.76" });

  it("pernas da casa selecionada nos três pares", () => {
    const v = buildPregaoView({ quotes: [usdPyg, usdBrl, brlPyg, bcpRef], sources, sessions: [], pair: "USD/PYG", selectedKey: null, now: NOW });
    expect(v.cross.house).toBe("Cambios Chaco");
    expect(v.cross.usdPyg).toEqual({ buy: "5905", sell: "5975", captured_at: usdPyg.captured_at });
    expect(v.cross.usdBrl).toEqual({ buy: "5.40", sell: "5.46", captured_at: usdBrl.captured_at });
    expect(v.cross.direct).toEqual({ buy: "1092", sell: "1112", captured_at: brlPyg.captured_at });
  });

  it("modalidade diferente não vira perna (contexto não se mistura)", () => {
    const usdBrlAccount = mkQuote({ id: "br2", source_id: "chaco", base: "USD", quote: "BRL", buy: "5.40", sell: "5.46", modality: "account" });
    const v = buildPregaoView({ quotes: [usdPyg, usdBrlAccount], sources, sessions: [], pair: "USD/PYG", selectedKey: null, now: NOW });
    expect(v.cross.usdPyg).not.toBeNull();
    expect(v.cross.usdBrl).toBeNull();
  });

  it("filial ou faixa de montante diferente não vira perna; mesma filial vira", () => {
    const atBranch = (p: Partial<Quote> & Pick<Quote, "id">) => mkQuote({ source_id: "chaco", branch_id: "chaco-cde-centro", ...p });
    const py = atBranch({ id: "py-b" });
    const brOther = atBranch({ id: "br-o", base: "USD", quote: "BRL", buy: "5.40", sell: "5.46", branch_id: "chaco-cde-shopping" });
    const brTier = atBranch({ id: "br-t", base: "USD", quote: "BRL", buy: "5.40", sell: "5.46", amount_base: "1000" });
    const brSame = atBranch({ id: "br-s", base: "USD", quote: "BRL", buy: "5.41", sell: "5.47" });
    const mixed = buildPregaoView({ quotes: [py, brOther, brTier], sources, sessions: [], pair: "USD/PYG", selectedKey: null, now: NOW });
    expect(mixed.cross.usdPyg).not.toBeNull();
    expect(mixed.cross.usdBrl).toBeNull();
    const same = buildPregaoView({ quotes: [py, brOther, brTier, brSame], sources, sessions: [], pair: "USD/PYG", selectedKey: null, now: NOW });
    expect(same.cross.usdBrl?.buy).toBe("5.41");
  });

  it("referência selecionada nunca é perna: o cartão usa a casa padrão do par", () => {
    const v = buildPregaoView({ quotes: [usdPyg, usdBrl, bcpRef], sources, sessions: [], pair: "USD/PYG", selectedKey: bcpRef.series_key, now: NOW });
    expect(v.effectiveKey).toBe(bcpRef.series_key);
    expect(v.cross.house).toBe("Cambios Chaco");
    expect(v.cross.usdPyg?.buy).toBe("5905");
  });
});

describe("buildPregaoView — sessões do par", () => {
  const sess = (source_id: string, status: HouseSession["status"], channel: HouseSession["channel"] = "physical", reference = false): HouseSession => ({
    source_id,
    name: source_id,
    city: null,
    tz: "America/Asuncion",
    channel,
    reference,
    status,
    opens_at: null,
    closes_at: null,
    next_change_at: null,
    data_mode: "real",
  });

  it("pairSessions traz só as casas com cotação no par atual: sem referência e sem casas que só cotam outro par", () => {
    const v = buildPregaoView({
      quotes: [mkQuote({ id: "q1", source_id: "chaco" }), mkQuote({ id: "q2", source_id: "nomad", base: "BRL", buy: "1.1", sell: "1.2", channel: "digital" })],
      sources: [src("chaco", "Cambios Chaco"), src("nomad", "Nomad", "fintech")],
      sessions: [sess("chaco", "open"), sess("nomad", "closed", "digital"), sess("bcp", "open", "digital", true)],
      pair: "USD/PYG",
      selectedKey: null,
      now: NOW,
    });
    expect(v.pairSessions.map((s) => s.source_id)).toEqual(["chaco"]);
  });
});

describe("cyclePair", () => {
  it("anda na sequência de PAIRS e dá a volta nos dois sentidos", () => {
    expect(cyclePair("USD/PYG", 1)).toBe("BRL/PYG");
    expect(cyclePair("BRL/PYG", 1)).toBe("USD/BRL");
    expect(cyclePair("USD/BRL", 1)).toBe("USD/PYG");
    expect(cyclePair("USD/PYG", -1)).toBe("USD/BRL");
  });
});
