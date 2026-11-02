import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { toNumber } from "@/lib/format";
import {
  DEFAULT_SERIES_KEY,
  DEMO_HOURS,
  DEMO_HOUSES,
  DEMO_HOUSE_IDS,
  dayStartAsuncion,
  demoBook,
  demoCandle,
  demoCandles,
  demoClose,
  demoHeat,
  demoPrints,
  demoQuotesAt,
  demoSeriesKeys,
  demoSessions,
  demoStats,
  demoTicker,
  demoWatchlist,
  drift,
  fnv1a,
  lcg,
} from "@/lib/pregao/demo";

const NOW = new Date(Date.UTC(2026, 10, 2, 12, 30));
const num = (s: string | null) => toNumber(s)!;

describe("PRNG determinístico", () => {
  it("fnv1a matches the 32-bit FNV-1a reference values", () => {
    expect(fnv1a("")).toBe(2166136261);
    expect(fnv1a("a")).toBe(0xe40c292c);
    expect(fnv1a("foobar")).toBe(0xbf9cf968);
  });
  it("lcg yields the same sequence in [0, 1) for the same seed", () => {
    const a = lcg(42);
    const b = lcg(42);
    const seq = [a(), a(), a()];
    expect(seq).toEqual([b(), b(), b()]);
    expect(seq.every((x) => x >= 0 && x < 1)).toBe(true);
    expect(lcg(7)()).not.toBe(lcg(8)());
  });
  it("drift stays within ±0.4 % and follows a weekly cycle", () => {
    for (let i = 0; i < 200; i++) {
      const d = drift(i, 3600);
      expect(d).toBeGreaterThanOrEqual(0.996);
      expect(d).toBeLessThanOrEqual(1.004);
    }
    expect(drift(0, 3600)).toBe(1);
    expect(drift(168, 3600)).toBeCloseTo(1, 9);
  });
});

describe("demoCandles", () => {
  const candles = demoCandles(DEFAULT_SERIES_KEY, "1h", NOW, 50);
  it("ends at bucketStart(now) inclusive with exactly count candles", () => {
    expect(candles).toHaveLength(50);
    expect(candles.at(-1)?.t).toBe("2026-11-02T12:00:00.000Z");
  });
  it("is strictly ascending in t", () => {
    for (let i = 1; i < candles.length; i++) expect(Date.parse(candles[i].t)).toBeGreaterThan(Date.parse(candles[i - 1].t));
  });
  it("respects OHLC and buy_c < c < sell_c invariants", () => {
    for (const c of candles) {
      const [o, h, l, cl] = [num(c.o), num(c.h), num(c.l), num(c.c)];
      expect(l).toBeLessThanOrEqual(Math.min(o, cl));
      expect(h).toBeGreaterThanOrEqual(Math.max(o, cl));
      expect(c.n).toBeGreaterThanOrEqual(1);
      expect(num(c.buy_c)).toBeLessThan(cl);
      expect(num(c.sell_c)).toBeGreaterThan(cl);
      expect(c.spread_avg).not.toBeNull();
      expect(c.data_mode).toBe("demo");
    }
  });
  it("opens where the previous candle closed", () => {
    expect(candles[10].o).toBe(candles[9].c);
    expect(num(demoCandle(DEFAULT_SERIES_KEY, "1h", 100).o)).toBeCloseTo(demoClose(DEFAULT_SERIES_KEY, "1h", 99), 4);
  });
  it("uses 4 decimal places at most and stays near the anchor", () => {
    for (const c of candles) {
      expect(c.c).toMatch(/^\d+(\.\d{1,4})?$/);
      expect(num(c.c)).toBeGreaterThan(5900);
      expect(num(c.c)).toBeLessThan(5980);
    }
    expect(num(demoCandles("nomad:digital:USD/BRL:account", "1d", NOW, 1)[0].c)).toBeCloseTo(5.43, 1);
  });
  it("is deterministic and differs per key", () => {
    expect(JSON.stringify(demoCandles(DEFAULT_SERIES_KEY, "1h", NOW, 50))).toBe(JSON.stringify(candles));
    expect(JSON.stringify(demoCandles("alberdi:CDE:USD/PYG:cash", "1h", NOW, 50))).not.toBe(JSON.stringify(candles));
  });
  it("skips Sunday buckets for physical keys but not for digital ones", () => {
    const monday = new Date(Date.UTC(2026, 10, 2));
    const chaco = demoCandles("chaco:CDE:USD/PYG:cash", "1d", monday, 7);
    expect(chaco).toHaveLength(7);
    expect(chaco.some((c) => c.t.startsWith("2026-11-01"))).toBe(false);
    expect(chaco.some((c) => c.t.startsWith("2026-10-25"))).toBe(false);
    const ueno = demoCandles("ueno:digital:USD/PYG:transfer", "1d", monday, 7);
    expect(ueno.some((c) => c.t.startsWith("2026-11-01"))).toBe(true);
  });
  it("returns [] for count 0", () => {
    expect(demoCandles(DEFAULT_SERIES_KEY, "15m", NOW, 0)).toEqual([]);
  });
});

describe("dayStartAsuncion", () => {
  it("is 00:00 in Asunción (UTC−3) of the local day containing now", () => {
    expect(dayStartAsuncion(NOW).toISOString()).toBe("2026-11-02T03:00:00.000Z");
    expect(dayStartAsuncion(new Date(Date.UTC(2026, 10, 2, 2, 30))).toISOString()).toBe("2026-11-01T03:00:00.000Z");
  });
});

describe("demoStats", () => {
  const stats = demoStats(DEFAULT_SERIES_KEY, NOW);
  it("summarises the local day", () => {
    expect(stats.n_quotes).toBeGreaterThan(0);
    expect(stats.houses).toBe(5);
    expect(stats.day_start.startsWith("2026-11-02T00:00:00")).toBe(true);
    expect(stats.day_start).toBe("2026-11-02T00:00:00-03:00");
    expect(stats).toMatchObject({ key: DEFAULT_SERIES_KEY, data_mode: "demo" });
    expect(stats.open).not.toBeNull();
    // última vela = bucket de 12:30 (inclusive); last_at = t + g − 1 s
    expect(stats.last_at).toBe("2026-11-02T12:44:59.000Z");
  });
  it("derives change and high/low from the 15m candles of the day", () => {
    const day = demoCandles(DEFAULT_SERIES_KEY, "15m", NOW, 96).filter((c) => Date.parse(c.t) >= Date.UTC(2026, 10, 2, 3));
    expect(stats.open).toBe(day[0].o);
    expect(stats.last).toBe(day.at(-1)!.c);
    expect(num(stats.high)).toBe(Math.max(...day.map((c) => num(c.h))));
    expect(num(stats.low)).toBe(Math.min(...day.map((c) => num(c.l))));
    expect(stats.n_quotes).toBe(day.reduce((s, c) => s + c.n, 0));
    expect(num(stats.change_abs)).toBeCloseTo(num(stats.last) - num(stats.open), 6);
    expect(num(stats.change_pct)).toBeCloseTo(((num(stats.last) - num(stats.open)) / num(stats.open)) * 100, 6);
  });
  it("is empty for a physical key on Sunday", () => {
    const sunday = demoStats(DEFAULT_SERIES_KEY, new Date(Date.UTC(2026, 10, 1, 15)));
    expect(sunday).toMatchObject({ open: null, high: null, low: null, last: null, last_at: null, change_abs: null, change_pct: null, n_quotes: 0, spread_avg: null, houses: 0 });
  });
});

describe("demoSessions", () => {
  const sessions = demoSessions(NOW);
  it("has one session per demo house with demo- ids", () => {
    expect(sessions).toHaveLength(DEMO_HOUSES.length);
    expect(sessions.every((s) => s.source_id.startsWith("demo-"))).toBe(true);
    expect(sessions.every((s) => s.data_mode === "demo")).toBe(true);
    expect(sessions.find((s) => s.source_id === "demo-bcp")?.reference).toBe(true);
    expect(sessions.filter((s) => s.reference)).toHaveLength(1);
  });
  it("uses the house hours for the status", () => {
    expect(sessions.find((s) => s.source_id === "demo-chaco")).toMatchObject({ status: "open", name: "Cambios Chaco", city: "CDE", tz: "America/Asuncion", channel: "physical", closes_at: "2026-11-02T20:00:00.000Z" });
    expect(sessions.find((s) => s.source_id === "demo-ueno")).toMatchObject({ status: "open", city: null, channel: "digital", opens_at: null });
  });
  it("DEMO_HOURS covers exactly the demo houses", () => {
    expect(Object.keys(DEMO_HOURS).sort()).toEqual([...DEMO_HOUSE_IDS].sort());
  });
});

describe("demoQuotesAt", () => {
  const quotes = demoQuotesAt(NOW);
  it("re-stamps the 15 house/reference quotes with deterministic ages between 30 s and 9.5 min", () => {
    expect(quotes).toHaveLength(15);
    expect(quotes.every((q) => q.data_mode === "demo")).toBe(true);
    expect(quotes.some((q) => q.source_id === "westernunion" || q.source_id === "revolut")).toBe(false);
    for (const q of quotes) {
      const age = (NOW.getTime() - Date.parse(q.captured_at)) / 1000;
      expect(age).toBeGreaterThanOrEqual(30);
      expect(age).toBeLessThanOrEqual(570);
    }
    expect(JSON.stringify(demoQuotesAt(NOW))).toBe(JSON.stringify(quotes));
  });
  it("demoSeriesKeys lists the house keys of a pair without references", () => {
    const keys = demoSeriesKeys("USD/PYG");
    expect(keys).toContain(DEFAULT_SERIES_KEY);
    expect(keys).toContain("ueno:digital:USD/PYG:account");
    expect(keys.some((k) => k.startsWith("bcp:"))).toBe(false);
    expect(new Set(keys).size).toBe(keys.length);
    expect(demoSeriesKeys("USD/BRL")).toEqual(["nomad:digital:USD/BRL:account"]);
    const bookKeys = demoBook("USD/PYG", NOW).filter((l) => l.kind !== "market_reference").map((l) => l.key);
    expect([...keys].sort()).toEqual([...bookKeys].sort());
  });
});

describe("visões demo", () => {
  it("demoBook has the reference only in bcp and resolved statuses", () => {
    const book = demoBook("USD/PYG", NOW);
    expect(book.filter((l) => l.kind === "market_reference").map((l) => l.source_id)).toEqual(["bcp"]);
    expect(book.at(-1)?.source_id).toBe("bcp");
    expect(book.find((l) => l.source_id === "chaco")?.status).toBe("open");
    expect(book.find((l) => l.source_id === "chaco")?.agio_buy_pct).not.toBeNull();
  });
  it("demoTicker covers every key once with change_pct from demoStats", () => {
    const items = demoTicker(NOW);
    expect(items).toHaveLength(15);
    expect(new Set(items.map((i) => i.key)).size).toBe(15);
    expect(items[0].pair).toBe("USD/PYG");
    expect(items.find((i) => i.key === DEFAULT_SERIES_KEY)?.change_pct).toBe(toNumber(demoStats(DEFAULT_SERIES_KEY, NOW).change_pct));
  });
  it("demoPrints are newest first with unique ids and chained prev_mid", () => {
    const prints = demoPrints(NOW, 10);
    expect(prints).toHaveLength(10);
    expect(new Set(prints.map((p) => p.id)).size).toBe(10);
    for (let i = 1; i < prints.length; i++) expect(Date.parse(prints[i].captured_at)).toBeLessThan(Date.parse(prints[i - 1].captured_at));
    expect(prints.every((p) => p.kind !== "market_reference" && p.data_mode === "demo")).toBe(true);
    expect(prints.every((p) => p.id.startsWith("demo-print-"))).toBe(true);
    const twenty = demoPrints(NOW, 20);
    const first = twenty[0];
    const older = twenty.slice(1).find((p) => p.key === first.key)!;
    expect(first.prev_mid).toBe(older.mid);
    expect(first.change_pct).not.toBeNull();
    expect(twenty.at(-1)?.prev_mid).toBeNull();
    expect(twenty.filter((p) => p.pair === "USD/PYG" && p.buy !== null).every((p) => /^\d+$/.test(p.buy!))).toBe(true);
  });
  it("demoWatchlist adds 24 sparkline points per row", () => {
    const rows = demoWatchlist("USD/PYG", NOW);
    expect(rows.length).toBeGreaterThan(1);
    expect(rows.every((r) => r.spark.length === 24)).toBe(true);
    expect(rows.find((r) => r.key === DEFAULT_SERIES_KEY)?.change_pct).not.toBeNull();
  });
  it("demoHeat has no reference and covers the three pairs", () => {
    const cells = demoHeat(NOW);
    expect(cells.some((c) => c.source_id === "bcp")).toBe(false);
    expect(new Set(cells.map((c) => c.pair))).toEqual(new Set(["USD/PYG", "BRL/PYG", "USD/BRL"]));
    expect(cells.find((c) => c.key === demoQuotesAt(NOW)[0].series_key)).toBeDefined();
  });
});

describe("fonte", () => {
  it("never reads the clock", () => {
    const src = readFileSync("src/lib/pregao/demo.ts", "utf8");
    expect(src).not.toMatch(/Date\.now\(\)|new Date\(\)/);
  });
});
