import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { API_BASE, ApiError, api, http, qs, resolveMode } from "@/lib/api/client";
import { watchApi } from "@/lib/api/watch";
import type { Quote } from "@/lib/api/types";

let fetchMock: ReturnType<typeof vi.fn>;
const json = (body: unknown, init: ResponseInit = {}) =>
  new Response(JSON.stringify(body), { status: 200, headers: { "content-type": "application/json" }, ...init });
const lastCall = () => fetchMock.mock.calls.at(-1) as [string, RequestInit | undefined];

beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

describe("http()", () => {
  it("uses the proxy base /api/fx when NEXT_PUBLIC_API_URL is unset", async () => {
    expect(API_BASE).toBe("/api/fx");
    fetchMock.mockImplementation(async () => json({ ok: 1 }));
    await expect(http("/v1/sources")).resolves.toEqual({ ok: 1 });
    expect(String(lastCall()[0])).toBe("/api/fx/v1/sources");
  });
  it("sends Content-Type only when there is a body", async () => {
    fetchMock.mockImplementation(async () => json([]));
    await http("/v1/sources");
    expect(new Headers(lastCall()[1]?.headers).has("content-type")).toBe(false);
    await http("/v1/journal", { method: "POST", body: JSON.stringify({ text: "x" }) });
    expect(new Headers(lastCall()[1]?.headers).get("content-type")).toBe("application/json");
  });
  it("resolves undefined on 204", async () => {
    fetchMock.mockImplementation(async () => new Response(null, { status: 204 }));
    await expect(http("/v1/alerts/rules/r1", { method: "DELETE" })).resolves.toBeUndefined();
  });
  it("throws ApiError with status and the backend detail", async () => {
    fetchMock.mockImplementation(async () => json({ detail: "fonte em modo demo" }, { status: 409 }));
    const err = await http("/v1/watch/run/chaco", { method: "POST" }).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(409);
    expect((err as ApiError).message).toMatch(/fonte em modo demo/);
  });
});

describe("qs()", () => {
  it("skips undefined, empty and 'all' and encodes the rest", () => {
    expect(qs({ a: "x y", b: undefined, c: "", d: "all", e: 5, f: null })).toBe("?a=x+y&e=5");
    expect(qs({})).toBe("");
  });
});

describe("resolveMode", () => {
  it("honours explicit choices and falls back to demo until the backend is known", () => {
    expect(resolveMode("demo", "available")).toBe("demo");
    expect(resolveMode("real", "unavailable")).toBe("real");
    expect(resolveMode("simulation", "unknown")).toBe("simulation");
    expect(resolveMode("auto", "unknown")).toBe("demo");
    expect(resolveMode("auto", "unavailable")).toBe("demo");
    expect(resolveMode("auto", "available")).toBe("real");
  });
});

describe("api filters are really sent", () => {
  it("quotes: amount and modality go to the query string; city=digital becomes a client-side null-city filter", async () => {
    fetchMock.mockImplementation(async () => json([]));
    await api.quotes("real", { city: "CDE", base: "USD", quote: "PYG", source: "chaco", modality: "cash", amount: "5000" });
    expect(String(lastCall()[0])).toBe("/api/fx/v1/quotes?city=CDE&base=USD&quote=PYG&source=chaco&modality=cash&amount=5000");
    const digital = { id: "a", city: null } as unknown as Quote;
    const cde = { id: "b", city: "CDE" } as unknown as Quote;
    fetchMock.mockImplementation(async () => json([digital, cde]));
    const out = await api.quotes("simulation", { city: "digital" });
    expect(String(lastCall()[0])).toBe("/api/fx/v1/quotes?data_mode=simulation");
    expect(out.map((q) => q.id)).toEqual(["a"]);
  });
  it("opportunities: capital, channel and city are sent (number or object form)", async () => {
    fetchMock.mockImplementation(async () => json([]));
    await api.opportunities("real", 5000);
    expect(String(lastCall()[0])).toBe("/api/fx/v1/opportunities?capital=5000");
    await api.opportunities("real", { capital: "25000", channel: "digital", city: "CDE" });
    expect(String(lastCall()[0])).toBe("/api/fx/v1/opportunities?capital=25000&channel=digital&city=CDE");
  });
  it("simulation mode is sent as data_mode and never mixed with real", async () => {
    fetchMock.mockImplementation(async () => json([]));
    await api.sources("simulation");
    expect(String(lastCall()[0])).toBe("/api/fx/v1/sources?data_mode=simulation");
    await api.sources("real");
    expect(String(lastCall()[0])).toBe("/api/fx/v1/sources");
  });
});

describe("api endpoints without a client until now", () => {
  it("cycles: max_len, min_roi (decimal string), start and limit", async () => {
    fetchMock.mockImplementation(async () => json([]));
    await api.cycles("real", { maxLen: 6, minRoi: "0.001", start: "BRL@brbank", limit: 50 });
    expect(String(lastCall()[0])).toBe("/api/fx/v1/opportunities/cycles?max_len=6&min_roi=0.001&start=BRL%40brbank&limit=50");
    await api.cycles("real", {});
    expect(String(lastCall()[0])).toBe("/api/fx/v1/opportunities/cycles?max_len=4");
  });
  it("cycles in demo mode come from the TS graph as D1 strings and never hit the network", async () => {
    const cycles = await api.cycles("demo", { maxLen: 4 });
    expect(fetchMock).not.toHaveBeenCalled();
    expect(cycles.length).toBeGreaterThan(0);
    for (const c of cycles) {
      expect(typeof c.amount_in).toBe("string");
      expect(typeof c.gain).toBe("string");
      expect(typeof c.roi).toBe("string");
      expect(c.data_mode).toBe("demo");
      expect(c.path[0]).toBe(c.start);
    }
    const limited = await api.cycles("demo", { limit: 1, minRoi: "-1" });
    expect(limited).toHaveLength(1);
  });
  it("branches, requestQuote, volatility, accounts, evidence, journal, rules, memory summary", async () => {
    fetchMock.mockImplementation(async () => json([]));
    await api.branches("real", "chaco");
    expect(String(lastCall()[0])).toBe("/api/fx/v1/sources/chaco/branches");

    fetchMock.mockImplementation(async () => json({ status: "queued", job_id: "j1" }));
    await api.requestQuote("real", { source_id: "westernunion", params: { amount: "5000" } });
    expect(String(lastCall()[0])).toBe("/api/fx/v1/quotes/request");
    expect(lastCall()[1]?.method).toBe("POST");
    expect(JSON.parse(String(lastCall()[1]?.body))).toEqual({ source_id: "westernunion", params: { amount: "5000" } });

    fetchMock.mockImplementation(async () => json({ key: "k", window: "1h" }));
    await api.volatility("real", "chaco:CDE:USD/PYG:cash", "24h");
    expect(String(lastCall()[0])).toBe("/api/fx/v1/volatility?key=chaco%3ACDE%3AUSD%2FPYG%3Acash&window=24h");

    fetchMock.mockImplementation(async () => json({ id: "acc-1" }));
    await api.createAccount("real", { institution: "ueno", label: "ueno PYG", currency: "PYG", kind: "bank", location: "ASU", balance_free: "1000", balance_reserved: "0", balance_in_transit: "0" });
    expect(String(lastCall()[0])).toBe("/api/fx/v1/accounts");
    expect(lastCall()[1]?.method).toBe("POST");
    await api.updateAccount("real", "acc-1", { balance_free: "1500" });
    expect(String(lastCall()[0])).toBe("/api/fx/v1/accounts/acc-1");
    expect(lastCall()[1]?.method).toBe("PATCH");
    expect(JSON.parse(String(lastCall()[1]?.body))).toEqual({ balance_free: "1500" });

    fetchMock.mockImplementation(async () => json([]));
    await api.evidence("real", { source: "chaco", from: "2026-11-01T00:00:00Z" });
    expect(String(lastCall()[0])).toBe("/api/fx/v1/evidence?source=chaco&from=2026-11-01T00%3A00%3A00Z");
    fetchMock.mockImplementation(async () => json({ id: "ev-1" }));
    await api.evidenceById("real", "ev-1");
    expect(String(lastCall()[0])).toBe("/api/fx/v1/evidence/ev-1");

    fetchMock.mockImplementation(async () => json({ id: "j-1" }));
    await api.createJournal("real", { kind: "note", text: "x", amounts: [], account_ids: [] });
    expect(String(lastCall()[0])).toBe("/api/fx/v1/journal");
    expect(lastCall()[1]?.method).toBe("POST");

    fetchMock.mockImplementation(async () => json({ id: "r1", enabled: false }));
    await api.updateRule("real", "r1", { enabled: false });
    expect(String(lastCall()[0])).toBe("/api/fx/v1/alerts/rules/r1");
    expect(lastCall()[1]?.method).toBe("PATCH");
    fetchMock.mockImplementation(async () => new Response(null, { status: 204 }));
    await expect(api.deleteRule("real", "r1")).resolves.toBeUndefined();
    expect(lastCall()[1]?.method).toBe("DELETE");

    fetchMock.mockImplementation(async () => json({ summary: "tudo bem" }));
    await expect(api.memorySummary("real", 20)).resolves.toEqual({ summary: "tudo bem" });
    expect(String(lastCall()[0])).toBe("/api/fx/v1/memory/summary?limit=20");
  });
  it("demo implementations never touch the network and stay flagged demo", async () => {
    const branches = await api.branches("demo", "chaco");
    expect(branches.every((b) => b.source_id === "chaco")).toBe(true);
    const req = await api.requestQuote("demo", { source_id: "chaco", params: {} });
    expect(["done", "queued", "blocked"]).toContain(req.status);
    const acc = await api.createAccount("demo", { institution: "x", label: "y", currency: "BRL", kind: "bank", location: "digital", balance_free: "1", balance_reserved: "0", balance_in_transit: "0" });
    expect(acc.id).toMatch(/^local-/);
    const upd = await api.updateAccount("demo", acc.id, { balance_free: "2" });
    expect(upd.balance_free).toBe("2");
    await expect(api.updateAccount("demo", "nope", { balance_free: "2" })).rejects.toBeInstanceOf(ApiError);
    const ev = await api.evidenceById("demo", "demo-ev-0");
    expect(ev.id).toBe("demo-ev-0");
    const j = await api.createJournal("demo", { kind: "note", text: "x", amounts: [], account_ids: [] });
    expect(j.id).toMatch(/^local-/);
    const rules = await watchApi.rules("demo");
    const r = await api.updateRule("demo", rules[0].id, { enabled: !rules[0].enabled });
    expect(r.enabled).toBe(!rules[0].enabled);
    expect(r.data_mode).toBe("demo");
    await api.deleteRule("demo", rules[0].id);
    expect((await watchApi.rules("demo")).some((x) => x.id === rules[0].id)).toBe(false);
    const vol = await api.volatility("demo", "chaco:CDE:USD/PYG:cash", "24h");
    expect(vol.window).toBe("24h");
    expect(typeof vol.coverage_pct).toBe("string");
    const mem = await api.memorySummary("demo");
    expect(typeof mem.summary).toBe("string");
    const health = await api.health("demo");
    expect(health?.data_mode).toBe("demo");
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("watchApi shares the single http()", () => {
  it("builds watch URLs on the proxy base and handles 200 null from a poll without change", async () => {
    fetchMock.mockImplementation(async () => new Response("null", { status: 200, headers: { "content-type": "application/json" } }));
    await expect(watchApi.triggerPoll("real", "chaco")).resolves.toBeNull();
    expect(String(lastCall()[0])).toBe("/api/fx/v1/watch/run/chaco");
    fetchMock.mockImplementation(async () => json([]));
    await watchApi.changes("real", { source: "chaco", kind: "all" });
    expect(String(lastCall()[0])).toBe("/api/fx/v1/watch/changes?source=chaco");
  });
});
