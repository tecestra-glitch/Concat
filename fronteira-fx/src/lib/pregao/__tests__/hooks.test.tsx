import { readFileSync } from "node:fs";
import { QueryClient } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DEFAULT_SERIES_KEY, demoStats } from "@/lib/pregao/demo";
import { TIMEFRAMES, type CandleSeries } from "@/lib/pregao/types";
import { candlesQueryOptions, pregaoKeys, refetchMsFor } from "@/lib/pregao/use-candles";
import { sessionsQueryOptions } from "@/lib/pregao/use-house-sessions";
import { statsByKey, statsQueryOptions } from "@/lib/pregao/use-session-stats";

const KEY = DEFAULT_SERIES_KEY;
const NOW = new Date(Date.UTC(2026, 10, 2, 12, 30));
const MIN_POLL_MS = 60_000;

const SERIE: CandleSeries = {
  key: "k",
  tf: "15m",
  candles: [{ t: "2026-11-02T12:00:00Z", o: "7335", h: "7337", l: "7318", c: "7318", n: 3, spread_avg: "30", buy_c: "7318", sell_c: "7352", data_mode: "real" }],
  data_mode: "real",
};

function response(body: unknown): Response {
  return { ok: true, status: 200, statusText: "OK", json: async () => body } as unknown as Response;
}

describe("intervalos de sondagem", () => {
  it("refetchMsFor: 15m usa 60 s; 1h, 4h e 1d usam 300 s", () => {
    expect(refetchMsFor("15m")).toBe(60_000);
    expect(refetchMsFor("1h")).toBe(300_000);
    expect(refetchMsFor("4h")).toBe(300_000);
    expect(refetchMsFor("1d")).toBe(300_000);
  });

  it("candlesQueryOptions usa staleTime igual ao refetchInterval de cada intervalo", () => {
    const fast = candlesQueryOptions("demo", KEY, "15m");
    expect(fast.refetchInterval).toBe(60_000);
    expect(fast.staleTime).toBe(60_000);
    for (const tf of ["1h", "4h", "1d"] as const) {
      const o = candlesQueryOptions("demo", KEY, tf);
      expect(o.refetchInterval).toBe(300_000);
      expect(o.staleTime).toBe(300_000);
    }
  });

  it("nenhum intervalo nem staleTime fica abaixo do piso de 60 s", () => {
    for (const tf of TIMEFRAMES) {
      const o = candlesQueryOptions("demo", KEY, tf);
      expect(o.refetchInterval).toBeGreaterThanOrEqual(MIN_POLL_MS);
      expect(o.staleTime).toBeGreaterThanOrEqual(MIN_POLL_MS);
    }
    const stats = statsQueryOptions("demo", [KEY]);
    expect(stats.refetchInterval).toBeGreaterThanOrEqual(MIN_POLL_MS);
    expect(stats.staleTime).toBeGreaterThanOrEqual(MIN_POLL_MS);
    const sessions = sessionsQueryOptions("demo");
    expect(sessions.refetchInterval).toBeGreaterThanOrEqual(MIN_POLL_MS);
    expect(sessions.staleTime).toBeGreaterThanOrEqual(MIN_POLL_MS);
  });
});

describe("chaves de query", () => {
  it("candles usa [pregao, candles, modo, chave, intervalo, limite]", () => {
    expect(candlesQueryOptions("demo", KEY, "15m").queryKey).toEqual(["pregao", "candles", "demo", KEY, "15m", 300]);
    expect(pregaoKeys.candles("real", "k", "1h", 10)).toEqual(["pregao", "candles", "real", "k", "1h", 10]);
  });

  it("stats e sessions incluem o modo na chave", () => {
    expect(pregaoKeys.stats("demo", [KEY, "x"])).toEqual(["pregao", "stats", "demo", `${KEY},x`]);
    expect(pregaoKeys.sessions("real")).toEqual(["pregao", "sessions", "real"]);
    expect(sessionsQueryOptions("demo").queryKey).toEqual(["pregao", "sessions", "demo"]);
  });
});

describe("stats: chave estável quando só a ordem das chaves muda (QA-5)", () => {
  const A = "alberdi:CDE:USD/PYG:cash";
  const B = "bonanza:ASU:USD/PYG:cash";

  it("a queryKey não depende da ordem (a lista vem ordenada por captured_at e muda a cada cotação)", () => {
    expect(statsQueryOptions("real", [B, KEY, A]).queryKey).toEqual(statsQueryOptions("real", [A, B, KEY]).queryKey);
  });

  it("o pedido sai com as chaves na mesma ordem da queryKey", async () => {
    const fetchMock = vi.fn<(input: string) => Promise<Response>>().mockResolvedValue(response([]));
    vi.stubGlobal("fetch", fetchMock);
    try {
      await new QueryClient().fetchQuery(statsQueryOptions("real", [B, KEY, A]));
      const url = new URL(String(fetchMock.mock.calls[0][0]), "http://localhost");
      expect(url.searchParams.get("keys")).toBe([A, B, KEY].join(","));
    } finally {
      vi.unstubAllGlobals();
    }
  });
});

describe("habilitação", () => {
  it("candles fica desabilitada sem chave ou com chave vazia", () => {
    expect(candlesQueryOptions("demo", null, "1h").enabled).toBe(false);
    expect(candlesQueryOptions("demo", "", "1h").enabled).toBe(false);
  });

  it("stats fica desabilitada sem chaves", () => {
    expect(statsQueryOptions("demo", []).enabled).toBe(false);
  });
});

describe("modo demo: sem rede", () => {
  const fetchMock = vi.fn<(input: string) => Promise<Response>>();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("candles demo devolve a quantidade pedida com data_mode demo", async () => {
    const series = await new QueryClient().fetchQuery(candlesQueryOptions("demo", KEY, "1h", 10));
    expect(series.candles).toHaveLength(10);
    expect(series.data_mode).toBe("demo");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("stats demo devolve uma entrada por chave, na mesma ordem", async () => {
    const keys = [KEY, "nomad:digital:USD/BRL:account"];
    const stats = await new QueryClient().fetchQuery(statsQueryOptions("demo", keys));
    expect(stats.map((s) => s.key)).toEqual(keys);
    expect(stats.every((s) => s.data_mode === "demo")).toBe(true);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("sessions demo devolve as sete casas do pregão demo", async () => {
    const sessions = await new QueryClient().fetchQuery(sessionsQueryOptions("demo"));
    expect(sessions).toHaveLength(7);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("modo real: chamada ao endpoint", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("candles real chama /v1/candles com key, tf e limit e devolve a série validada", async () => {
    const fetchMock = vi.fn<(input: string) => Promise<Response>>(async () => response(SERIE));
    vi.stubGlobal("fetch", fetchMock);
    const series = await new QueryClient().fetchQuery(candlesQueryOptions("real", "k", "15m", 5));
    expect(series).toEqual(SERIE);
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain("/v1/candles?key=k&tf=15m&limit=5");
  });
});

describe("funções puras de apoio", () => {
  it("statsByKey indexa por chave e aceita ausência de dados", () => {
    expect(statsByKey(undefined).size).toBe(0);
    const stats = [demoStats(KEY, NOW), demoStats("nomad:digital:USD/BRL:account", NOW)];
    const map = statsByKey(stats);
    expect(map.size).toBe(2);
    expect(map.get(KEY)).toBe(stats[0]);
  });
});

describe("fonte dos hooks", () => {
  it("os três arquivos de hooks não usam useEffect nem useState", () => {
    for (const file of ["use-candles.ts", "use-session-stats.ts", "use-house-sessions.ts"]) {
      const src = readFileSync(new URL(`../${file}`, import.meta.url), "utf8");
      expect(src, file).not.toMatch(/useEffect|useState\(/);
    }
  });
});
