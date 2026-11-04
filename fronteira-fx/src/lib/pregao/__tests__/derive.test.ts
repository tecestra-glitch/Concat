import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { Quote, Source } from "@/lib/api/types";
import { demoSources, seriesKey } from "@/lib/api/demo-data";
import { AgioBadge, agioLabel } from "@/components/pregao/agio-badge";
import { Delta, deltaText, directionOf } from "@/components/pregao/delta";
import { ReferenceBadge } from "@/components/pregao/reference-badge";
import { demoQuotesAt, demoSessions } from "@/lib/pregao/demo";
import {
  agioPct,
  defaultKeyFor,
  houseName,
  isIncomplete,
  pctChange,
  quoteToPrint,
  refMidFor,
  spreadPct,
  statusOf,
  toBookLevels,
  toHeatCells,
  toTickerItems,
  toWatchlistRows,
} from "@/lib/pregao/derive";
import type { HouseSession, SessionStats } from "@/lib/pregao/types";

const NOW = new Date(Date.UTC(2026, 10, 2, 12, 0));
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

function mkSession(source_id: string, status: HouseSession["status"]): HouseSession {
  return { source_id, name: source_id, city: "CDE", tz: "America/Asuncion", channel: "physical", reference: false, status, opens_at: null, closes_at: null, next_change_at: null, data_mode: "real" };
}

const sources: Source[] = [
  { id: "chaco", name: "Cambios Chaco", kind: "exchange_house", method: "html", integration: "html", url: "", health: "ok", last_success_at: null, last_error: null, capabilities: [], limitations: [], coverage: { cities: ["CDE"], currencies: ["USD", "PYG"] }, poll_interval_s: 300, data_mode: "real" },
  { id: "bcp", name: "BCP (referência)", kind: "central_bank", method: "html", integration: "api_oficial", url: "", health: "ok", last_success_at: null, last_error: null, capabilities: [], limitations: [], coverage: { cities: [], currencies: ["USD", "PYG"] }, poll_interval_s: 3600, data_mode: "real" },
];

const chacoOld = mkQuote({ id: "q-chaco-old", source_id: "chaco", buy: "5900", sell: "5970", captured_at: ago(900) });
const chaco = mkQuote({ id: "q-chaco", source_id: "chaco" });
const alberdi = mkQuote({ id: "q-alberdi", source_id: "alberdi", buy: "5915", sell: "5965", captured_at: ago(200) });
const uenoHalf = mkQuote({ id: "q-ueno", source_id: "ueno", city: null, buy: "5880", sell: null, modality: "account", channel: "digital", captured_at: ago(60) });
const bcp = mkQuote({ id: "q-bcp", source_id: "bcp", city: null, buy: "5944.76", sell: "5944.76", modality: "transfer", kind: "market_reference", channel: "digital", captured_at: ago(900) });
const brl = mkQuote({ id: "q-chaco-brl", source_id: "chaco", base: "BRL", buy: "1092", sell: "1112" });
const eur = mkQuote({ id: "q-eur", source_id: "chaco", base: "USD", quote: "BRL", buy: "5.40", sell: "5.46", city: null, channel: "digital", modality: "account" });
const quotes = [chacoOld, chaco, alberdi, uenoHalf, bcp, brl, eur];
const sessions = [mkSession("chaco", "closed"), mkSession("alberdi", "open")];

describe("fórmulas de §0.8", () => {
  it("spreadPct is (sell − buy) / mid · 100", () => {
    expect(spreadPct("5905", "5975")).toBeCloseTo(1.1784, 3);
    expect(spreadPct(null, "5975")).toBeNull();
    expect(spreadPct("0", "0")).toBeNull();
    expect(spreadPct("-5", "5")).toBeNull();
  });
  it("agioPct against the reference mid", () => {
    expect(agioPct("5905", 5944.76)).toBeCloseTo(-0.66882, 4);
    expect(agioPct("5975", 5944.76)).toBeCloseTo(0.50868, 4);
    expect(agioPct(null, 5944.76)).toBeNull();
    expect(agioPct("5905", null)).toBeNull();
    expect(agioPct("5905", 0)).toBeNull();
  });
  it("pctChange", () => {
    expect(pctChange(100, 101)).toBe(1);
    expect(pctChange(0, 5)).toBeNull();
    expect(pctChange(null, 5)).toBeNull();
    expect(pctChange(5, null)).toBeNull();
  });
  it("isIncomplete when a side is missing", () => {
    expect(isIncomplete({ buy: "1", sell: "2" })).toBe(false);
    expect(isIncomplete({ buy: null, sell: "2" })).toBe(true);
  });
});

describe("lookups", () => {
  it("houseName falls back to the id", () => {
    expect(houseName(sources, "chaco")).toBe("Cambios Chaco");
    expect(houseName(sources, "zzz")).toBe("zzz");
  });
  it("statusOf is unknown for a missing source and tolerates the demo- prefix", () => {
    expect(statusOf(sessions, "alberdi")).toBe("open");
    expect(statusOf(sessions, "norte")).toBe("unknown");
    expect(statusOf([mkSession("demo-chaco", "pre")], "chaco")).toBe("pre");
  });
  it("refMidFor picks the freshest reference of the pair and ignores stale ones", () => {
    expect(refMidFor(quotes, "USD/PYG", NOW)).toBe(5944.76);
    expect(refMidFor(quotes, "BRL/PYG", NOW)).toBeNull();
    const stale = { ...bcp, captured_at: ago(25 * 3600) };
    expect(refMidFor([chaco, stale], "USD/PYG", NOW)).toBeNull();
  });
  it("refMidFor prefers bcp over dolarpy", () => {
    const dolarpy = mkQuote({ id: "q-dpy", source_id: "dolarpy", kind: "market_reference", buy: "6000", sell: "6000", city: null, channel: "digital", captured_at: ago(10) });
    expect(refMidFor([dolarpy, bcp], "USD/PYG", NOW)).toBe(5944.76);
    expect(refMidFor([dolarpy], "USD/PYG", NOW)).toBe(6000);
  });
  it("refMidFor skips a stale bcp and falls back to a fresh dolarpy", () => {
    const dolarpy = mkQuote({ id: "q-dpy", source_id: "dolarpy", kind: "market_reference", buy: "6000", sell: "6000", city: null, channel: "digital", captured_at: ago(10) });
    const staleBcp = { ...bcp, captured_at: ago(30 * 3600) };
    expect(refMidFor([staleBcp, dolarpy], "USD/PYG", NOW)).toBe(6000);
  });
});

describe("toBookLevels", () => {
  const levels = toBookLevels(quotes, "USD/PYG", sources, sessions, NOW);
  it("keeps one level per key, most recent first, references last", () => {
    expect(levels.map((l) => l.source_id)).toEqual(["ueno", "chaco", "alberdi", "bcp"]);
    expect(levels.find((l) => l.source_id === "chaco")?.buy).toBe("5905");
    expect(levels.every((l) => l.pair === "USD/PYG")).toBe(true);
  });
  it("derives spread, agio, status, house and incomplete", () => {
    const c = levels.find((l) => l.source_id === "chaco")!;
    expect(c).toMatchObject({ key: chaco.series_key, house: "Cambios Chaco", status: "closed", incomplete: false, channel: "physical", kind: "indicative", city: "CDE", data_mode: "real" });
    expect(c.spread_pct).toBeCloseTo(1.1784, 3);
    expect(c.agio_buy_pct).toBeCloseTo(-0.66882, 4);
    expect(c.agio_sell_pct).toBeCloseTo(0.50868, 4);
    const u = levels.find((l) => l.source_id === "ueno")!;
    expect(u).toMatchObject({ incomplete: true, spread_pct: null, agio_sell_pct: null, status: "unknown", house: "ueno" });
    expect(u.agio_buy_pct).not.toBeNull();
  });
  it("keeps the reference with null agio", () => {
    const r = levels.find((l) => l.source_id === "bcp")!;
    expect(r).toMatchObject({ kind: "market_reference", agio_buy_pct: null, agio_sell_pct: null });
  });
});

describe("toTickerItems", () => {
  it("one per key, pairs in PAIRS order, houses before references, houses by source_id", () => {
    const stats = new Map<string, SessionStats>([[chaco.series_key, { key: chaco.series_key, day_start: "", open: null, high: null, low: null, last: null, last_at: null, change_abs: null, change_pct: "0.0681663", n_quotes: 4, spread_avg: null, houses: 1, data_mode: "real" }]]);
    const items = toTickerItems(quotes, sources, stats);
    expect(items.map((i) => `${i.pair} ${i.source_id}`)).toEqual(["USD/PYG alberdi", "USD/PYG chaco", "USD/PYG ueno", "USD/PYG bcp", "BRL/PYG chaco", "USD/BRL chaco"]);
    const c = items.find((i) => i.key === chaco.series_key)!;
    expect(c).toMatchObject({ mid: 5940, buy: "5905", incomplete: false, house: "Cambios Chaco" });
    expect(c.change_pct).toBeCloseTo(0.0681663, 6);
    expect(items.find((i) => i.source_id === "alberdi")?.change_pct).toBeNull();
  });
});

describe("toWatchlistRows / toHeatCells", () => {
  const levels = toBookLevels(quotes, "USD/PYG", sources, sessions, NOW);
  it("adds change_pct and spark", () => {
    const rows = toWatchlistRows(levels, new Map(), { [chaco.series_key]: [1, 2, 3] });
    expect(rows.find((r) => r.source_id === "chaco")).toMatchObject({ change_pct: null, spark: [1, 2, 3] });
    expect(rows.find((r) => r.source_id === "alberdi")?.spark).toEqual([]);
  });
  it("heat cells exclude references", () => {
    const cells = toHeatCells(levels);
    expect(cells.some((c) => c.source_id === "bcp")).toBe(false);
    expect(cells.find((c) => c.source_id === "chaco")).toMatchObject({ pair: "USD/PYG", house: "Cambios Chaco", status: "closed" });
    expect(cells.find((c) => c.source_id === "chaco")?.spread_pct).toBeCloseTo(1.1784, 3);
  });
});

describe("quoteToPrint", () => {
  it("computes change_pct from prev", () => {
    const p = quoteToPrint(chaco, chacoOld, "Cambios Chaco")!;
    expect(p).toMatchObject({ id: "q-chaco", key: chaco.series_key, pair: "USD/PYG", mid: 5940, prev_mid: 5935, house: "Cambios Chaco", incomplete: false });
    expect(p.change_pct).toBeCloseTo((5940 / 5935 - 1) * 100, 9);
  });
  it("has null prev_mid/change_pct without prev", () => {
    expect(quoteToPrint(chaco, null, "x")).toMatchObject({ prev_mid: null, change_pct: null });
  });
  it("drops pairs outside PAIRS", () => {
    expect(quoteToPrint(mkQuote({ id: "q-x", source_id: "chaco", base: "USD", quote: "USD" }), null, "x")).toBeNull();
  });
});

describe("defaultKeyFor", () => {
  it("prefers the first open house, then the first house, never a reference", () => {
    const levels = toBookLevels(quotes, "USD/PYG", sources, sessions, NOW);
    expect(defaultKeyFor(levels)).toBe(alberdi.series_key);
    const closed = toBookLevels(quotes, "USD/PYG", sources, [], NOW);
    expect(defaultKeyFor(closed)).toBe(uenoHalf.series_key);
    expect(defaultKeyFor(toBookLevels([bcp], "USD/PYG", sources, [], NOW))).toBeNull();
    expect(defaultKeyFor([])).toBeNull();
  });
});

describe("com as cotações demo (§2.8 item 22)", () => {
  const levels = toBookLevels(demoQuotesAt(NOW), "USD/PYG", demoSources, demoSessions(NOW), NOW);
  it("has one level per key, bcp as reference without agio, houses with numeric agio", () => {
    expect(new Set(levels.map((l) => l.key)).size).toBe(levels.length);
    const ref = levels.find((l) => l.source_id === "bcp")!;
    expect(ref).toMatchObject({ kind: "market_reference", agio_buy_pct: null, agio_sell_pct: null });
    for (const l of levels.filter((l) => l.source_id !== "bcp")) expect(typeof l.agio_buy_pct).toBe("number");
    expect(levels.every((l) => l.data_mode === "demo")).toBe(true);
  });
  it("defaultKeyFor returns a house key, not bcp", () => {
    const key = defaultKeyFor(levels)!;
    expect(key).not.toBeNull();
    expect(key.startsWith("bcp:")).toBe(false);
    expect(levels.find((l) => l.key === key)?.status).toBe("open");
  });
});

describe("componentes compartilhados (§2.7, item 24)", () => {
  it("Delta renders direction, sign and screen-reader text", () => {
    const up = renderToStaticMarkup(createElement(Delta, { value: 0.84 }));
    expect(up).toContain('data-testid="pregao-delta"');
    expect(up).toContain('data-direction="up"');
    expect(up).toContain("+0,84");
    expect(up).toContain(" subiu");
    expect(up).toContain("text-gain");
    const down = renderToStaticMarkup(createElement(Delta, { value: "-0.66882" }));
    expect(down).toContain('data-direction="down"');
    expect(down).toContain("−0,67");
    expect(down).toContain(" caiu");
    expect(down).toContain("text-loss");
    const flat = renderToStaticMarkup(createElement(Delta, { value: 0 }));
    expect(flat).toContain('data-direction="flat"');
    expect(flat).toContain(" estável");
    const none = renderToStaticMarkup(createElement(Delta, { value: null }));
    expect(none).toContain('data-direction="none"');
    expect(none).toContain("—");
    expect(none).toContain("sem variação disponível");
  });
  it("Delta kind=abs formats a rate with sign", () => {
    expect(deltaText(5, "abs", "PYG")).toBe("+5");
    expect(deltaText(-0.0123, "abs", "BRL")).toBe("−0,0123");
    expect(deltaText(0, "abs", "PYG")).toBe("0");
    expect(deltaText(null, "abs", "PYG")).toBe("—");
    expect(deltaText(0.84, "pct")).toBe("+0,84 %");
    expect(renderToStaticMarkup(createElement(Delta, { value: "5", kind: "abs", quote: "PYG" }))).toContain("+5");
  });
  it("Delta kind=abs in PYG derives arrow and sign from the rounded value", () => {
    const tiny = renderToStaticMarkup(createElement(Delta, { value: 0.3, kind: "abs", quote: "PYG" }));
    expect(tiny).toContain('data-direction="flat"');
    expect(tiny).toContain(" estável");
    expect(tiny).not.toContain("+0");
    expect(deltaText(0.3, "abs", "PYG")).toBe("0");
    expect(deltaText(-0.4, "abs", "PYG")).toBe("0");
    expect(deltaText(0.6, "abs", "PYG")).toBe("+1");
    expect(renderToStaticMarkup(createElement(Delta, { value: 0.3, kind: "abs", quote: "BRL" }))).toContain('data-direction="up"');
  });
  it("directionOf", () => {
    expect(directionOf(null)).toBe("none");
    expect(directionOf(1e-12)).toBe("flat");
    expect(directionOf(0.1)).toBe("up");
    expect(directionOf(-0.1)).toBe("down");
  });
  it("AgioBadge", () => {
    const neg = renderToStaticMarkup(createElement(AgioBadge, { value: -0.66882 }));
    expect(neg).toContain('data-testid="pregao-agio-badge"');
    expect(neg).toContain("−0,67");
    expect(neg).toContain("abaixo da referência");
    expect(renderToStaticMarkup(createElement(AgioBadge, { value: 0.50868 }))).toContain("acima da referência");
    expect(agioLabel(0)).toEqual({ text: "0,00 %", sr: "igual à referência" });
    expect(agioLabel(null)).toEqual({ text: "—", sr: "sem referência" });
    expect(agioLabel(0.50868).text).toBe("+0,51 %");
  });
  it("ReferenceBadge", () => {
    const compact = renderToStaticMarkup(createElement(ReferenceBadge, { compact: true }));
    expect(compact).toContain('data-testid="pregao-reference-badge"');
    expect(compact).toMatch(/<span class="sr-only">Referência<\/span>/);
    expect(compact).toContain('data-compact="true"');
    expect(compact).toContain("Não é executável.");
    const full = renderToStaticMarkup(createElement(ReferenceBadge, { source: "BCP" }));
    expect(full).toContain("Fonte: BCP.");
    expect(full).not.toContain('class="sr-only"');
    expect(full).toContain("Referência");
  });
});
