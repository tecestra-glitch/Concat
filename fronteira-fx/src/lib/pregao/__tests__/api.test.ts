import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { API_BASE, ApiError } from "@/lib/api/client";
import { STATS_BATCH, fetchCandles, fetchSessions, fetchStats } from "@/lib/pregao/api";
import { DEFAULT_SERIES_KEY, DEMO_HOURS, demoSessions } from "@/lib/pregao/demo";
import {
  CandleSchema,
  CandleSeriesSchema,
  HouseHoursSchema,
  HouseSessionSchema,
  SessionStatsSchema,
  decStr,
  isoDate,
  type CandleJson,
  type CandleSeriesJson,
  type HouseHoursJson,
  type HouseSessionJson,
  type SessionStatsJson,
} from "@/lib/pregao/schemas";
import type { Candle, CandleSeries, HouseHours, HouseSession, SessionStats } from "@/lib/pregao/types";

// Compatibilidade de tipos (só compila): o JSON validado é atribuível ao tipo do contrato.
const _c: Candle = {} as CandleJson;
const _cs: CandleSeries = {} as CandleSeriesJson;
const _ss: SessionStats = {} as SessionStatsJson;
const _hh: HouseHours = {} as HouseHoursJson;
const _hs: HouseSession = {} as HouseSessionJson;
void [_c, _cs, _ss, _hh, _hs];

const NOW = new Date(Date.UTC(2026, 10, 2, 12, 30));

const CANDLE = { t: "2026-11-02T12:00:00Z", o: "7335", h: "7337", l: "7318", c: "7318", n: 3, spread_avg: "30", buy_c: "7318", sell_c: "7352", data_mode: "real" as const };
const SERIES = { key: "k", tf: "1h" as const, candles: [CANDLE], data_mode: "real" as const };
const STATS = { key: "a", day_start: "2026-11-02T00:00:00-03:00", open: "7335", high: "7340", low: "7318", last: "7340", last_at: "2026-11-02T12:16:00Z", change_abs: "5", change_pct: "0.0681663", n_quotes: 4, spread_avg: "30", houses: 1, data_mode: "real" as const };
const SESSION = { source_id: "chaco", name: "Cambios Chaco", city: "CDE" as const, tz: "America/Asuncion", channel: "physical" as const, reference: false, status: "open" as const, opens_at: "2026-11-02T10:30:00Z", closes_at: "2026-11-02T20:00:00Z", next_change_at: "2026-11-02T20:00:00Z", data_mode: "real" as const };

function response(status: number, body?: unknown) {
  const statusText = status === 200 ? "OK" : status === 404 ? "Not Found" : status === 500 ? "Internal Server Error" : "Error";
  return { ok: status >= 200 && status < 300, status, statusText, json: async () => body } as unknown as Response;
}

const fetchMock = vi.fn<typeof fetch>();
const urlOf = (call: number) => String(fetchMock.mock.calls[call]?.[0]);
const paramsOf = (call: number) => new URL(urlOf(call), "http://local").searchParams;

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  vi.unstubAllGlobals();
});

describe("schemas zod", () => {
  it("decStr accepts decimal strings only", () => {
    expect(decStr.safeParse("7335").success).toBe(true);
    expect(decStr.safeParse("-0.5").success).toBe(true);
    expect(decStr.safeParse("1e5").success).toBe(false);
    expect(decStr.safeParse("abc").success).toBe(false);
    expect(decStr.safeParse(7335).success).toBe(false);
  });
  it("isoDate accepts parseable dates", () => {
    expect(isoDate.safeParse("2026-11-02T12:00:00Z").success).toBe(true);
    expect(isoDate.safeParse("ontem").success).toBe(false);
  });
  it("validates the canonical candle and rejects n = 0", () => {
    expect(CandleSchema.safeParse(CANDLE).success).toBe(true);
    expect(CandleSchema.safeParse({ ...CANDLE, n: 0 }).success).toBe(false);
    expect(CandleSchema.safeParse({ ...CANDLE, spread_avg: undefined }).success).toBe(false);
    expect(CandleSeriesSchema.safeParse({ ...SERIES, tf: "5m" }).success).toBe(false);
  });
  it("validates stats, sessions and hours", () => {
    expect(SessionStatsSchema.safeParse(STATS).success).toBe(true);
    expect(SessionStatsSchema.safeParse({ ...STATS, houses: -1 }).success).toBe(false);
    expect(HouseSessionSchema.safeParse(SESSION).success).toBe(true);
    expect(HouseSessionSchema.safeParse({ ...SESSION, status: "aberta" }).success).toBe(false);
    expect(HouseHoursSchema.safeParse(DEMO_HOURS.chaco).success).toBe(true);
    expect(HouseHoursSchema.safeParse({ ...DEMO_HOURS.chaco, days: [0] }).success).toBe(false);
  });
});

describe("fetchCandles", () => {
  it("demo mode uses the local generator and never calls fetch", async () => {
    const s = await fetchCandles("demo", DEFAULT_SERIES_KEY, "1h", { now: NOW, limit: 10 });
    expect(fetchMock).not.toHaveBeenCalled();
    expect(s).toMatchObject({ key: DEFAULT_SERIES_KEY, tf: "1h", data_mode: "demo" });
    expect(s.candles).toHaveLength(10);
    expect(s.candles.at(-1)?.t).toBe("2026-11-02T12:00:00.000Z");
  });
  it("real mode builds the URL, sends JSON headers and returns the validated series", async () => {
    fetchMock.mockResolvedValueOnce(response(200, SERIES));
    const s = await fetchCandles("real", "k", "1h", { limit: 10 });
    expect(urlOf(0).endsWith("/v1/candles?key=k&tf=1h&limit=10")).toBe(true);
    expect((fetchMock.mock.calls[0]?.[1] as RequestInit).headers).toMatchObject({ "content-type": "application/json" });
    expect(s).toEqual(SERIES);
  });
  it("passes from/to and the AbortSignal, omitting undefined params", async () => {
    fetchMock.mockResolvedValueOnce(response(200, SERIES));
    const ctl = new AbortController();
    await fetchCandles("real", "k", "15m", { from: "2026-11-02T00:00:00Z", to: "2026-11-02T12:00:00Z", signal: ctl.signal });
    const p = paramsOf(0);
    expect([...p.keys()]).toEqual(["key", "tf", "from", "to"]);
    expect(p.get("from")).toBe("2026-11-02T00:00:00Z");
    expect((fetchMock.mock.calls[0]?.[1] as RequestInit).signal).toBe(ctl.signal);
  });
  it("throws ApiError(0, contrato inválido …) when the contract is broken", async () => {
    fetchMock.mockResolvedValueOnce(response(200, { ...SERIES, candles: [{ ...CANDLE, n: 0 }] }));
    const err = await fetchCandles("real", "k", "1h").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(0);
    expect((err as ApiError).message.startsWith("contrato inválido em /v1/candles")).toBe(true);
  });
  it("throws ApiError with the HTTP status on failure", async () => {
    fetchMock.mockResolvedValueOnce(response(500));
    const err = await fetchCandles("real", "k", "1h").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(500);
    expect((err as ApiError).message).toBe("500 Internal Server Error em /v1/candles");
  });
  it("falls back to /v1/history aggregated locally on 404", async () => {
    fetchMock.mockResolvedValueOnce(response(404));
    fetchMock.mockResolvedValueOnce(
      response(200, {
        key: "k",
        points: [
          { t: "2026-11-02T12:01:00Z", buy: "7320", sell: "7350", mid: null },
          { t: "2026-11-02T12:06:00Z", buy: "7322", sell: "7352", mid: null },
          { t: "2026-11-02T12:11:00Z", buy: "7318", sell: null, mid: null },
          { t: "2026-11-02T12:16:00Z", buy: "7325", sell: "7355", mid: null },
        ],
      }),
    );
    const s = await fetchCandles("real", "k", "15m", { limit: 1 });
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(urlOf(1).endsWith("/v1/history?key=k&grid=300")).toBe(true);
    expect(s).toEqual({ key: "k", tf: "15m", data_mode: "real", candles: [{ t: "2026-11-02T12:15:00.000Z", o: "7340", h: "7340", l: "7340", c: "7340", n: 1, spread_avg: "30", buy_c: "7325", sell_c: "7355", data_mode: "real" }] });
  });
  it("applies from (inclusive) and to (exclusive) to the history fallback", async () => {
    fetchMock.mockResolvedValueOnce(response(404));
    fetchMock.mockResolvedValueOnce(
      response(200, {
        key: "k",
        points: [
          { t: "2026-11-02T11:59:00Z", buy: "1", sell: "1", mid: null },
          { t: "2026-11-02T12:00:00Z", buy: "7320", sell: "7350", mid: null },
          { t: "2026-11-02T12:16:00Z", buy: "7325", sell: "7355", mid: null },
          { t: "2026-11-02T12:30:00Z", buy: "9", sell: "9", mid: null },
        ],
      }),
    );
    const s = await fetchCandles("real", "k", "15m", { from: "2026-11-02T12:00:00Z", to: "2026-11-02T12:30:00Z" });
    expect(urlOf(1).endsWith("/v1/history?key=k&grid=300")).toBe(true);
    expect(s.candles.map((c) => [c.t, c.c])).toEqual([
      ["2026-11-02T12:00:00.000Z", "7335"],
      ["2026-11-02T12:15:00.000Z", "7340"],
    ]);
  });
  it("turns a non-JSON 200 body into ApiError(0, contrato inválido …)", async () => {
    fetchMock.mockResolvedValueOnce({ ok: true, status: 200, statusText: "OK", json: async () => { throw new SyntaxError("Unexpected token <"); } } as unknown as Response);
    const err = await fetchCandles("real", "k", "1h").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(0);
    expect((err as ApiError).message.startsWith("contrato inválido em /v1/candles")).toBe(true);
  });
  it("validates the history fallback too", async () => {
    fetchMock.mockResolvedValueOnce(response(404));
    fetchMock.mockResolvedValueOnce(response(200, { key: "k", points: [{ t: "x", buy: null, sell: null, mid: null }] }));
    const err = await fetchCandles("real", "k", "15m").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).message.startsWith("contrato inválido em /v1/history")).toBe(true);
  });
});

describe("fetchStats", () => {
  it("returns [] for no keys without network", async () => {
    expect(await fetchStats("real", [])).toEqual([]);
    expect(fetchMock).not.toHaveBeenCalled();
  });
  it("sends keys joined by comma and returns the validated list", async () => {
    fetchMock.mockResolvedValueOnce(response(200, [STATS, { ...STATS, key: "b" }]));
    const out = await fetchStats("real", ["a", "b"]);
    expect(urlOf(0)).toContain("/v1/pregao/stats?");
    expect(paramsOf(0).get("keys")).toBe("a,b");
    expect(out.map((s) => s.key)).toEqual(["a", "b"]);
  });
  it("returns [] on 404", async () => {
    fetchMock.mockResolvedValueOnce(response(404));
    expect(await fetchStats("real", ["a"])).toEqual([]);
  });
  it("keeps the batches already fetched when a later batch returns 404", async () => {
    const keys = Array.from({ length: 25 }, (_, i) => `k${i}`);
    fetchMock.mockImplementationOnce(async (url) => {
      const ks = new URL(String(url), "http://local").searchParams.get("keys")!.split(",");
      return response(200, ks.map((k) => ({ ...STATS, key: k })));
    });
    fetchMock.mockResolvedValueOnce(response(404));
    const out = await fetchStats("real", keys);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(out.map((s) => s.key)).toEqual(keys.slice(0, 20));
  });
  it("splits more than STATS_BATCH keys into sequential batches and concatenates in order", async () => {
    expect(STATS_BATCH).toBe(20);
    const keys = Array.from({ length: 45 }, (_, i) => `k${i}`);
    fetchMock.mockImplementation(async (url) => {
      const ks = new URL(String(url), "http://local").searchParams.get("keys")!.split(",");
      return response(200, ks.map((k) => ({ ...STATS, key: k })));
    });
    const out = await fetchStats("real", keys);
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(paramsOf(0).get("keys")!.split(",")).toHaveLength(20);
    expect(paramsOf(2).get("keys")!.split(",")).toHaveLength(5);
    expect(out.map((s) => s.key)).toEqual(keys);
  });
  it("rejects a broken contract", async () => {
    fetchMock.mockResolvedValueOnce(response(200, [{ ...STATS, n_quotes: "4" }]));
    const err = await fetchStats("real", ["a"]).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).message.startsWith("contrato inválido em /v1/pregao/stats")).toBe(true);
  });
  it("demo mode uses demoStats for each key", async () => {
    const out = await fetchStats("demo", [DEFAULT_SERIES_KEY, "alberdi:CDE:USD/PYG:cash"], { now: NOW });
    expect(fetchMock).not.toHaveBeenCalled();
    expect(out.map((s) => s.key)).toEqual([DEFAULT_SERIES_KEY, "alberdi:CDE:USD/PYG:cash"]);
    expect(out.every((s) => s.data_mode === "demo")).toBe(true);
  });
});

describe("fetchSessions", () => {
  it("real mode fetches /v1/pregao/sessions", async () => {
    fetchMock.mockResolvedValueOnce(response(200, [SESSION]));
    const out = await fetchSessions("real");
    expect(urlOf(0).endsWith("/v1/pregao/sessions")).toBe(true);
    expect(out).toEqual([SESSION]);
  });
  it("returns [] on 404 and throws on other errors", async () => {
    fetchMock.mockResolvedValueOnce(response(404));
    expect(await fetchSessions("real")).toEqual([]);
    fetchMock.mockResolvedValueOnce(response(500));
    await expect(fetchSessions("real")).rejects.toBeInstanceOf(ApiError);
  });
  it("demo mode returns demoSessions(now)", async () => {
    const out = await fetchSessions("demo", { now: NOW });
    expect(fetchMock).not.toHaveBeenCalled();
    expect(out).toEqual(demoSessions(NOW));
  });
});

describe("proxy e modo simulation (D3)", () => {
  it("goes through API_BASE (the /api/fx proxy unless NEXT_PUBLIC_API_URL is set)", async () => {
    fetchMock.mockResolvedValueOnce(response(200, [SESSION]));
    await fetchSessions("real");
    expect(urlOf(0)).toBe(`${API_BASE}/v1/pregao/sessions`);
  });
  it("real mode sends no data_mode; simulation sends ?data_mode=simulation on every route", async () => {
    fetchMock.mockResolvedValueOnce(response(200, SERIES));
    await fetchCandles("real", "k", "1h");
    expect(paramsOf(0).has("data_mode")).toBe(false);
    fetchMock.mockReset();
    fetchMock.mockResolvedValueOnce(response(200, { ...SERIES, data_mode: "simulation" }));
    fetchMock.mockResolvedValueOnce(response(200, [{ ...STATS, data_mode: "simulation" }]));
    fetchMock.mockResolvedValueOnce(response(200, [{ ...SESSION, data_mode: "simulation" }]));
    await fetchCandles("simulation", "k", "1h");
    await fetchStats("simulation", ["a"]);
    await fetchSessions("simulation");
    for (const call of [0, 1, 2]) expect(paramsOf(call).get("data_mode")).toBe("simulation");
  });
  it("labels the /v1/history fallback with the requested mode", async () => {
    fetchMock.mockResolvedValueOnce(response(404));
    fetchMock.mockResolvedValueOnce(response(200, { key: "k", points: [{ t: "2026-11-02T12:01:00Z", buy: "7320", sell: "7350", mid: null }] }));
    const s = await fetchCandles("simulation", "k", "15m");
    expect(paramsOf(1).get("data_mode")).toBe("simulation");
    expect(s.data_mode).toBe("simulation");
    expect(s.candles.every((c) => c.data_mode === "simulation")).toBe(true);
  });
});
