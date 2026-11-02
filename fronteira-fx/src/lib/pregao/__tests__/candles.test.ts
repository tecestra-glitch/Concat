import { describe, expect, it } from "vitest";
import type { HistoryPoint } from "@/lib/api/types";
import {
  aggregateHistory,
  baseOfPair,
  bucketStart,
  midOf,
  pairKeyOf,
  pairOf,
  quoteOfPair,
  tailLimit,
  toDecStr,
} from "@/lib/pregao/candles";

/** Cotações canônicas de §0.4 (`mid` nulo para forçar `midOf`), embaralhadas de propósito. */
const POINTS: HistoryPoint[] = [
  { t: "2026-11-02T12:16:00Z", buy: "7325", sell: "7355", mid: null },
  { t: "2026-11-02T12:01:00Z", buy: "7320", sell: "7350", mid: null },
  { t: "2026-11-02T12:11:00Z", buy: "7318", sell: null, mid: null },
  { t: "2026-11-02T12:06:00Z", buy: "7322", sell: "7352", mid: null },
];

describe("toDecStr", () => {
  it("drops trailing zeros and the decimal point", () => {
    expect(toDecStr(7335)).toBe("7335");
    expect(toDecStr(0.1 + 0.2)).toBe("0.3");
    expect(toDecStr(5.431)).toBe("5.431");
  });
  it("normalises negative zero", () => {
    expect(toDecStr(-0)).toBe("0");
    expect(toDecStr(-0.00000000001)).toBe("0");
  });
  it("rounds to the requested places", () => {
    expect(toDecStr(1.5, 0)).toBe("2");
    expect(toDecStr(5944.76, 4)).toBe("5944.76");
  });
  it("rejects NaN and Infinity", () => {
    expect(() => toDecStr(NaN)).toThrow(RangeError);
    expect(() => toDecStr(Infinity)).toThrow(RangeError);
  });
});

describe("midOf", () => {
  it("averages both sides", () => {
    expect(midOf("7320", "7350")).toBe(7335);
  });
  it("uses the present side when only one exists", () => {
    expect(midOf(null, "7350")).toBe(7350);
    expect(midOf("7318", null)).toBe(7318);
  });
  it("is null without sides", () => {
    expect(midOf(null, null)).toBeNull();
  });
});

describe("bucketStart", () => {
  it("aligns to the grid in UTC", () => {
    const ms = Date.UTC(2026, 10, 2, 12, 7, 31);
    expect(bucketStart(ms, 900)).toBe(Date.UTC(2026, 10, 2, 12, 0));
    expect(bucketStart(ms, 3600)).toBe(Date.UTC(2026, 10, 2, 12, 0));
    expect(bucketStart(ms, 86400)).toBe(Date.UTC(2026, 10, 2));
  });
  it("handles timestamps before the epoch", () => {
    expect(bucketStart(-1, 900)).toBe(-900_000);
  });
});

describe("pair helpers", () => {
  it("reads the pair segment of a series key", () => {
    expect(pairOf("chaco:CDE:USD/PYG:cash")).toBe("USD/PYG");
    expect(pairOf("chaco:CDE")).toBe("");
  });
  it("maps to PairKey or null", () => {
    expect(pairKeyOf("chaco:CDE:USD/PYG:cash")).toBe("USD/PYG");
    expect(pairKeyOf("x:y:EUR/PYG:cash")).toBeNull();
  });
  it("splits quote and base currency", () => {
    expect(quoteOfPair("USD/BRL")).toBe("BRL");
    expect(quoteOfPair("USD/PYG")).toBe("PYG");
    expect(baseOfPair("BRL/PYG")).toBe("BRL");
    expect(baseOfPair("USD/BRL")).toBe("USD");
  });
});

describe("aggregateHistory", () => {
  it("builds the two 15m buckets of §0.4", () => {
    const out = aggregateHistory(POINTS, "15m");
    expect(out).toEqual([
      { t: "2026-11-02T12:00:00.000Z", o: "7335", h: "7337", l: "7318", c: "7318", n: 3, spread_avg: "30", buy_c: "7318", sell_c: "7352", data_mode: "real" },
      { t: "2026-11-02T12:15:00.000Z", o: "7340", h: "7340", l: "7340", c: "7340", n: 1, spread_avg: "30", buy_c: "7325", sell_c: "7355", data_mode: "real" },
    ]);
  });
  it("builds the single 1h bucket of §0.4 and keeps the data_mode parameter", () => {
    const out = aggregateHistory(POINTS, "1h", "demo");
    expect(out).toEqual([
      { t: "2026-11-02T12:00:00.000Z", o: "7335", h: "7340", l: "7318", c: "7340", n: 4, spread_avg: "30", buy_c: "7325", sell_c: "7355", data_mode: "demo" },
    ]);
  });
  it("prefers the point's own mid when present", () => {
    const out = aggregateHistory([{ t: "2026-11-02T12:01:00Z", buy: "10", sell: "20", mid: "12.5" }], "15m");
    expect(out[0]?.c).toBe("12.5");
  });
  it("skips points without any side and never emits empty buckets", () => {
    const out = aggregateHistory(
      [
        { t: "2026-11-02T12:01:00Z", buy: null, sell: null, mid: null },
        { t: "2026-11-02T13:01:00Z", buy: "7320", sell: "7350", mid: null },
      ],
      "15m",
    );
    expect(out.map((c) => c.t)).toEqual(["2026-11-02T13:00:00.000Z"]);
    expect(out[0]).toMatchObject({ n: 1, spread_avg: "30" });
  });
  it("does not mutate the input order", () => {
    const copy = POINTS.map((p) => ({ ...p }));
    aggregateHistory(copy, "15m");
    expect(copy.map((p) => p.t)).toEqual(POINTS.map((p) => p.t));
  });
});

describe("tailLimit", () => {
  it("keeps the tail", () => {
    expect(tailLimit([1, 2, 3], 2)).toEqual([2, 3]);
    expect(tailLimit([1, 2, 3], 5)).toEqual([1, 2, 3]);
  });
  it("returns [] for a limit below 1", () => {
    expect(tailLimit([1], 0)).toEqual([]);
    expect(tailLimit([1], -3)).toEqual([]);
  });
});
