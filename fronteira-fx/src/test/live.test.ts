import { QueryClient } from "@tanstack/react-query";
import { describe, expect, it } from "vitest";
import { applyQuoteUpdate, applySnapshot, applySourceHealthEvent, mergeQuote, parseStreamFrame, quoteMatchesFilters, shouldResetCursor } from "@/lib/live-cache";
import { alertToasts } from "@/lib/alert-toasts";
import type { Quote, Snapshot, Source } from "@/lib/api/types";

const q = (over: Partial<Quote>): Quote => ({
  id: "q1",
  series_key: "chaco:CDE:USD/PYG:cash",
  source_id: "chaco",
  branch_id: null,
  city: "CDE",
  base: "USD",
  quote: "PYG",
  buy: "7300",
  sell: "7350",
  unit_note: "PYG por 1 USD",
  amount_base: null,
  modality: "cash",
  kind: "executable",
  channel: "physical",
  context: null,
  fees: [],
  captured_at: "2026-11-02T12:00:00Z",
  declared_updated_at: null,
  valid_until: null,
  evidence_id: "ev",
  data_mode: "real",
  ...over,
});

describe("quoteMatchesFilters", () => {
  it("matches on source, city, pair, modality and amount; ignores 'all' and empty", () => {
    const quote = q({});
    expect(quoteMatchesFilters(quote, {})).toBe(true);
    expect(quoteMatchesFilters(quote, { city: "all", source: "", base: undefined })).toBe(true);
    expect(quoteMatchesFilters(quote, { city: "CDE", base: "USD", quote: "PYG", source: "chaco", modality: "cash" })).toBe(true);
    expect(quoteMatchesFilters(quote, { city: "ASU" })).toBe(false);
    expect(quoteMatchesFilters(quote, { source: "alberdi" })).toBe(false);
    expect(quoteMatchesFilters(quote, { base: "BRL" })).toBe(false);
    expect(quoteMatchesFilters(quote, { modality: "account" })).toBe(false);
  });
  it("city=digital means city null; amount compares decimal strings numerically", () => {
    expect(quoteMatchesFilters(q({ city: null }), { city: "digital" })).toBe(true);
    expect(quoteMatchesFilters(q({ city: "CDE" }), { city: "digital" })).toBe(false);
    expect(quoteMatchesFilters(q({ amount_base: "5000" }), { amount: "5000.00" })).toBe(true);
    expect(quoteMatchesFilters(q({ amount_base: "5000" }), { amount: 10000 })).toBe(false);
    // Q-06: same rule as the backend's latest_quotes — a quote without amount is generic and stays in the list
    expect(quoteMatchesFilters(q({ amount_base: null }), { amount: "5000" })).toBe(true);
  });
});

describe("mergeQuote", () => {
  it("replaces the quote of the same series and appends a new series", () => {
    const a = q({ id: "a", series_key: "s1", sell: "7350" });
    const b = q({ id: "b", series_key: "s2" });
    const a2 = q({ id: "a-new", series_key: "s1", sell: "7360" });
    const out = mergeQuote([a, b], a2);
    expect(out).toHaveLength(2);
    expect(out.find((x) => x.series_key === "s1")?.sell).toBe("7360");
    expect(mergeQuote([a], b).map((x) => x.id)).toEqual(["a", "b"]);
    expect(mergeQuote(undefined, b)).toEqual([b]);
  });
});

describe("applyQuoteUpdate", () => {
  it("writes only into quote queries of the same mode whose filters match", () => {
    const qc = new QueryClient();
    qc.setQueryData(["quotes", "real", { city: "CDE" }], []);
    qc.setQueryData(["quotes", "real", { city: "ASU" }], []);
    qc.setQueryData(["quotes", "real", {}], []);
    qc.setQueryData(["quotes", "demo", {}], []);
    qc.setQueryData(["history", "real", "chaco:CDE:USD/PYG:cash"], { key: "chaco:CDE:USD/PYG:cash", points: [] });
    applyQuoteUpdate(qc, "real", q({}));
    expect(qc.getQueryData<Quote[]>(["quotes", "real", { city: "CDE" }])).toHaveLength(1);
    expect(qc.getQueryData<Quote[]>(["quotes", "real", { city: "ASU" }])).toHaveLength(0);
    expect(qc.getQueryData<Quote[]>(["quotes", "real", {}])).toHaveLength(1);
    expect(qc.getQueryData<Quote[]>(["quotes", "demo", {}])).toHaveLength(0);
    expect(qc.getQueryState(["history", "real", "chaco:CDE:USD/PYG:cash"])?.isInvalidated).toBe(true);
    expect(qc.getQueryCache().findAll({ queryKey: ["quotes"] })).toHaveLength(4); // no new keys were created
  });
  it("does not seed a quote list that is still loading (query without data)", () => {
    const qc = new QueryClient();
    qc.getQueryCache().build(qc, { queryKey: ["quotes", "real", { city: "CDE" }] });
    applyQuoteUpdate(qc, "real", q({}));
    expect(qc.getQueryData(["quotes", "real", { city: "CDE" }])).toBeUndefined();
    expect(qc.getQueryCache().findAll({ queryKey: ["quotes"] })).toHaveLength(1);
  });
});

describe("parseStreamFrame", () => {
  const frame = (over: Record<string, unknown>) => JSON.stringify({ type: "heartbeat", ts: "2026-11-02T12:00:00Z", payload: {}, ...over });
  it("keeps the id carried in the JSON body", () => {
    expect(parseStreamFrame(frame({ id: "ev-7" }), "sse-9")?.id).toBe("ev-7");
  });
  it("falls back to the SSE last event id when the body has no usable id", () => {
    expect(parseStreamFrame(frame({}), "sse-9")?.id).toBe("sse-9");
    expect(parseStreamFrame(frame({ id: "" }), "sse-9")?.id).toBe("sse-9");
    expect(parseStreamFrame(frame({ id: null }), "sse-9")?.id).toBe("sse-9");
  });
  it("rejects malformed JSON, unknown event types and frames without any id", () => {
    expect(parseStreamFrame("{not json", "sse-9")).toBeNull();
    expect(parseStreamFrame(frame({ id: "x", type: "bogus" }), "sse-9")).toBeNull();
    expect(parseStreamFrame(frame({}), "")).toBeNull();
  });
});

describe("applySnapshot", () => {
  const snap: Snapshot = {
    cursor: "c1",
    server_time: "2026-11-02T12:00:00Z",
    quotes: [q({ id: "cde", city: "CDE" }), q({ id: "asu", city: "ASU", series_key: "norte:ASU:USD/PYG:cash", source_id: "norte" })],
    sources: [],
    opportunities: [],
  };
  it("fills only the active queries of that mode, filtered per key", () => {
    const qc = new QueryClient();
    qc.setQueryData(["quotes", "real", { city: "CDE" }], []);
    qc.setQueryData(["quotes", "demo", {}], [q({ id: "demo-q", data_mode: "demo" })]);
    qc.setQueryData(["sources", "real"], []);
    applySnapshot(qc, "real", snap);
    expect(qc.getQueryData<Quote[]>(["quotes", "real", { city: "CDE" }])?.map((x) => x.id)).toEqual(["cde"]);
    expect(qc.getQueryData<Quote[]>(["quotes", "demo", {}])?.map((x) => x.id)).toEqual(["demo-q"]);
    expect(qc.getQueryData(["sources", "real"])).toEqual([]);
    expect(qc.getQueryCache().findAll({ queryKey: ["quotes"] })).toHaveLength(2);
    expect(qc.getQueryCache().findAll({ queryKey: ["opportunities"] })).toHaveLength(0);
  });
});

describe("source.health (Q-02)", () => {
  const src = (id: string, over: Partial<Source> = {}): Source => ({
    id,
    name: id.toUpperCase(),
    kind: "exchange_house",
    method: "html",
    url: `https://${id}.example`,
    health: "ok",
    last_success_at: "2026-11-02T11:00:00Z",
    last_error: null,
    capabilities: ["buy_sell"],
    limitations: [],
    coverage: { cities: ["CDE"], currencies: ["USD", "PYG"] },
    poll_interval_s: 300,
    data_mode: "real",
    ...over,
  });
  // exactly what services/collector.py emits (no `id`, not a full Source)
  const frame = (payload: unknown) =>
    parseStreamFrame(JSON.stringify({ id: "19", type: "source.health", ts: "2026-11-02T12:00:00Z", payload }), "")!;

  it("merges the backend payload into the cached Source by source_id and keeps the rest of it", () => {
    const qc = new QueryClient();
    qc.setQueryData<Source[]>(["sources", "real"], [src("chaco"), src("bcp")]);
    const ev = frame({ source_id: "chaco", health: "blocked", last_error: "403 anti-bot", consecutive_failures: 2, next_poll_at: "2026-11-02T12:10:00Z" });
    expect(applySourceHealthEvent(qc, "real", ev.payload)).toBe(true);
    const [chaco, bcp] = qc.getQueryData<Source[]>(["sources", "real"])!;
    expect(chaco.health).toBe("blocked");
    expect(chaco.last_error).toBe("403 anti-bot");
    expect(chaco.name).toBe("CHACO");
    expect(chaco.capabilities).toEqual(["buy_sell"]);
    expect(bcp).toEqual(src("bcp"));
  });

  it("ignores malformed payloads and lists of another mode", () => {
    const qc = new QueryClient();
    qc.setQueryData<Source[]>(["sources", "real"], [src("chaco")]);
    expect(applySourceHealthEvent(qc, "real", { id: "chaco", health: "blocked" })).toBe(false);
    expect(applySourceHealthEvent(qc, "real", { source_id: "chaco", health: "on fire", last_error: null })).toBe(false);
    expect(applySourceHealthEvent(qc, "simulation", frame({ source_id: "chaco", health: "blocked", last_error: null }).payload)).toBe(true);
    expect(qc.getQueryData<Source[]>(["sources", "real"])![0].health).toBe("ok");
  });
});

describe("shouldResetCursor", () => {
  it("treats a closed EventSource (HTTP error such as 410) as an expired cursor", () => {
    expect(shouldResetCursor(2)).toBe(true); // EventSource.CLOSED
    expect(shouldResetCursor(0)).toBe(false); // CONNECTING: the browser will retry by itself
  });
});

describe("alertToasts store", () => {
  it("pushes, lists newest first, dismisses and notifies subscribers", () => {
    alertToasts.clear();
    let notified = 0;
    const unsub = alertToasts.subscribe(() => notified++);
    alertToasts.push({ id: "e1", rule_id: "r1", ts: "2026-11-02T12:00:00Z", message: "um", payload: {}, channel: "ui", delivered: true, error: null, data_mode: "real" });
    alertToasts.push({ id: "e2", rule_id: "r1", ts: "2026-11-02T12:00:01Z", message: "dois", payload: {}, channel: "ui", delivered: true, error: null, data_mode: "real" });
    alertToasts.push({ id: "e2", rule_id: "r1", ts: "2026-11-02T12:00:01Z", message: "dois", payload: {}, channel: "ui", delivered: true, error: null, data_mode: "real" }); // duplicate
    expect(alertToasts.get().map((t) => t.id)).toEqual(["e2", "e1"]);
    expect(notified).toBe(2);
    alertToasts.dismiss("e2");
    expect(alertToasts.get().map((t) => t.id)).toEqual(["e1"]);
    const snapshot = alertToasts.get();
    expect(alertToasts.get()).toBe(snapshot); // stable reference for useSyncExternalStore
    unsub();
    alertToasts.clear();
    expect(notified).toBe(3);
  });
});
