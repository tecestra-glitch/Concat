import { describe, expect, it } from "vitest";
import { GRID_MS, computeVolatility, dedupeStale } from "@/lib/volatility";

const now = Date.parse("2026-11-02T12:00:00Z");
function series(n: number, f: (i: number) => number) {
  return Array.from({ length: n }, (_, i) => ({ t: now - (n - 1 - i) * GRID_MS, value: f(i) }));
}

describe("computeVolatility", () => {
  it("flags insufficient data below 6 returns", () => {
    const r = computeVolatility(series(5, (i) => 7300 + i), 60 * 60 * 1000, now);
    expect(r.status).toBe("insufficient_data");
    expect(r.stdevPctPer5m).toBeNull();
    expect(r.returnsUsed).toBe(4);
  });
  it("computes sample stdev of log returns on a 5-min grid", () => {
    const r = computeVolatility(series(13, (i) => (i % 2 === 0 ? 7300 : 7373)), 60 * 60 * 1000, now);
    expect(r.status).toBe("ok");
    // alternating ±1% log returns -> stdev about 1.0%
    expect(r.stdevPctPer5m!).toBeGreaterThan(0.95);
    expect(r.stdevPctPer5m!).toBeLessThan(1.05);
    expect(r.coveragePct).toBe(100);
  });
  it("reports gaps and coverage", () => {
    const s = series(13, (i) => 7300 + i * 2).filter((_, i) => i !== 5 && i !== 6);
    const r = computeVolatility(s, 60 * 60 * 1000, now);
    expect(r.gaps).toBe(1);
    expect(r.coveragePct).toBeLessThan(100);
  });
  it("does not treat a re-captured stale quote as a new observation", () => {
    const stale = series(13, () => 7300).map((o) => ({ ...o, declared: "2026-11-02T08:00:00Z" }));
    expect(dedupeStale(stale)).toHaveLength(1);
    const r = computeVolatility(stale, 60 * 60 * 1000, now);
    expect(r.status).toBe("stale_input");
  });
});
