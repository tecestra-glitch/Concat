import { beforeEach, describe, expect, it } from "vitest";
import {
  countRecent,
  formatClock,
  formatCountdown,
  formatInterval,
  formatThreshold,
  matchesChange,
  median,
  secondsUntil,
  summarizeWatch,
  validateTarget,
  validateThreshold,
  watchApi,
  type Change,
  type WatchStatus,
} from "@/lib/api/watch";
import { ApiError, api } from "@/lib/api/client";
import {
  buildDemoWatch,
  demoAlertEvents,
  demoAlertRules,
  demoChanges,
  demoCreateRule,
  demoTestRule,
  demoTriggerPoll,
  demoUpdateWatch,
  demoWatchStatuses,
  resetDemoWatch,
} from "@/lib/api/demo-watch";
import { demoEvidence, demoSources } from "@/lib/api/demo-data";
import { parseDecimalPtBR } from "@/lib/format";

const NOW = Date.parse("2026-11-02T12:00:00.000Z");
const at = (offsetS: number) => new Date(NOW + offsetS * 1000).toISOString();

describe("formatCountdown", () => {
  it("says agora once the target has passed", () => {
    expect(formatCountdown(at(-5), NOW)).toBe("agora");
    expect(formatCountdown(at(0), NOW)).toBe("agora");
  });
  it("counts seconds below a minute", () => {
    expect(formatCountdown(at(42), NOW)).toBe("42 s");
  });
  it("uses m:ss below an hour so it visibly ticks", () => {
    expect(formatCountdown(at(125), NOW)).toBe("2:05");
    expect(formatCountdown(at(600), NOW)).toBe("10:00");
  });
  it("uses hours and zero-padded minutes above an hour", () => {
    expect(formatCountdown(at(3900), NOW)).toBe("1 h 05 min");
  });
  it("handles missing or invalid dates", () => {
    expect(formatCountdown(null, NOW)).toBe("—");
    expect(formatCountdown("nope", NOW)).toBe("—");
    expect(secondsUntil("nope", NOW)).toBeNull();
  });
});

describe("formatInterval", () => {
  it("formats seconds, minutes and hours in pt-BR style", () => {
    expect(formatInterval(45)).toBe("45 s");
    expect(formatInterval(120)).toBe("2 min");
    expect(formatInterval(90)).toBe("1 min 30 s");
    expect(formatInterval(3600)).toBe("1 h");
    expect(formatInterval(5400)).toBe("1 h 30 min");
    expect(formatInterval(null)).toBe("—");
  });
});

describe("formatClock", () => {
  it("renders hh:mm:ss and tolerates garbage", () => {
    expect(formatClock(at(0))).toMatch(/^\d{2}:\d{2}:\d{2}$/);
    expect(formatClock("x")).toBe("—");
    expect(formatClock(null)).toBe("—");
  });
});

describe("thresholds", () => {
  it("formats ratios as pt-BR percent and source_down as duration", () => {
    expect(formatThreshold("cycle_roi", "0.002")).toBe("0,20 %");
    expect(formatThreshold("quote_move", "0.005")).toBe("0,50 %");
    expect(formatThreshold("opportunity_new", "0.0000074")).toBe("0,00074 %");
    expect(formatThreshold("source_down", "900")).toBe("15 min");
    expect(formatThreshold("source_down", null)).toBe("—");
  });
  it("thresholds are parsed with the shared pt-BR decimal parser", () => {
    expect(parseDecimalPtBR("0,25")).toBe("0.25");
    expect(parseDecimalPtBR("0.25")).toBe("0.25");
    expect(parseDecimalPtBR("1.250,5")).toBe("1250.5");
    expect(parseDecimalPtBR(" 15 ")).toBe("15");
    expect(parseDecimalPtBR("")).toBeNull();
    expect(parseDecimalPtBR("abc")).toBeNull();
    expect(parseDecimalPtBR("1,2,3")).toBeNull();
    expect(validateThreshold("cycle_roi", "1.250,5").ok).toBe(false); // > 100 %
    expect(validateThreshold("source_down", "1.000")).toEqual({ ok: true, value: "60000" });
  });
  it("converts a percent to a ratio string for ratio kinds", () => {
    expect(validateThreshold("cycle_roi", "0,25")).toEqual({ ok: true, value: "0.0025" });
    expect(validateThreshold("quote_move", "0.5")).toEqual({ ok: true, value: "0.005" });
    expect(validateThreshold("opportunity_new", "1")).toEqual({ ok: true, value: "0.01" });
  });
  it("rejects non-numbers, zero, negatives and more than 100 %", () => {
    for (const raw of ["abc", "", "0", "-1", "150"]) {
      const v = validateThreshold("cycle_roi", raw);
      expect(v.ok).toBe(false);
      if (!v.ok) expect(v.error).toMatch(/percentual/);
    }
  });
  it("takes integer minutes for source_down and stores seconds", () => {
    expect(validateThreshold("source_down", "15")).toEqual({ ok: true, value: "900" });
    expect(validateThreshold("source_down", "2,5").ok).toBe(false);
    expect(validateThreshold("source_down", "0").ok).toBe(false);
    expect(validateThreshold("source_down", "2000").ok).toBe(false);
  });
});

describe("validateTarget", () => {
  it("needs no target for the UI channel", () => {
    expect(validateTarget("ui", "anything")).toEqual({ ok: true, value: null });
  });
  it("checks each channel's format", () => {
    expect(validateTarget("telegram", "123456789")).toEqual({ ok: true, value: "123456789" });
    expect(validateTarget("telegram", "@fronteira_fx")).toEqual({ ok: true, value: "@fronteira_fx" });
    expect(validateTarget("telegram", "abc").ok).toBe(false);
    expect(validateTarget("webhook", "https://hooks.example.test/x")).toEqual({ ok: true, value: "https://hooks.example.test/x" });
    expect(validateTarget("webhook", "ftp://x").ok).toBe(false);
    expect(validateTarget("email", "a@b.co")).toEqual({ ok: true, value: "a@b.co" });
    expect(validateTarget("email", "a@b").ok).toBe(false);
    expect(validateTarget("email", "").ok).toBe(false);
  });
});

describe("summaries", () => {
  const status = (p: Partial<WatchStatus>): WatchStatus => ({
    source_id: "x",
    enabled: true,
    interval_s: 120,
    min_interval_s: 60,
    max_interval_s: 900,
    next_run_at: at(60),
    last_run_at: at(-60),
    last_change_at: null,
    changes_24h: 0,
    errors_in_row: 0,
    etag: null,
    content_hash: null,
    status: "ok",
    data_mode: "demo",
    ...p,
  });
  it("median handles odd, even and empty", () => {
    expect(median([])).toBeNull();
    expect(median([5, 1, 3])).toBe(3);
    expect(median([1, 2, 3, 4])).toBe(2.5);
  });
  it("groups states and takes the median of enabled intervals only", () => {
    const s = summarizeWatch([
      status({ status: "ok", interval_s: 120 }),
      status({ status: "degraded", interval_s: 600 }),
      status({ status: "stale", interval_s: 3600 }),
      status({ status: "blocked", interval_s: 900, enabled: false }),
      status({ status: "error", interval_s: 60 }),
    ]);
    expect(s).toEqual({ ok: 1, degraded: 2, blocked: 2, enabled: 4, medianIntervalS: 360 });
  });
  it("counts recent changes inside the window and filters by source/kind/from", () => {
    const ch = (p: Partial<Change>): Change => ({ id: "c", source_id: "chaco", ts: at(-10), kind: "quote_change", summary: "", before: {}, after: {}, evidence_id: null, data_mode: "demo", ...p });
    const list = [ch({ ts: at(-10) }), ch({ ts: at(-3000) }), ch({ ts: at(-4000) }), ch({ ts: at(30) })];
    expect(countRecent(list, NOW, 3600)).toBe(2);
    expect(matchesChange(ch({}), { source: "all", kind: "all" })).toBe(true);
    expect(matchesChange(ch({}), { source: "alberdi" })).toBe(false);
    expect(matchesChange(ch({ kind: "layout_change" }), { kind: "quote_change" })).toBe(false);
    expect(matchesChange(ch({ ts: at(-100) }), { from: at(-50) })).toBe(false);
  });
});

describe("demo watch dataset", () => {
  const ANCHOR = Date.parse("2026-11-02T12:00:00.000Z");

  beforeEach(() => resetDemoWatch());

  it("is deterministic for a given anchor", () => {
    expect(buildDemoWatch(ANCHOR)).toEqual(buildDemoWatch(ANCHOR));
  });
  it("flags every row as demo", () => {
    const { statuses, changes } = buildDemoWatch(ANCHOR);
    expect(statuses.length).toBeGreaterThanOrEqual(5);
    expect(statuses.every((s) => s.data_mode === "demo")).toBe(true);
    expect(changes.length).toBeGreaterThan(0);
    expect(changes.every((c) => c.data_mode === "demo")).toBe(true);
    expect(demoAlertRules().every((r) => r.data_mode === "demo")).toBe(true);
    expect(demoAlertEvents(ANCHOR).every((e) => e.data_mode === "demo")).toBe(true);
    expect(demoWatchStatuses().every((s) => s.data_mode === "demo")).toBe(true);
    expect(demoChanges().every((c) => c.data_mode === "demo")).toBe(true);
  });
  it("covers every demo source exactly once with a coherent schedule", () => {
    const { statuses } = buildDemoWatch(ANCHOR);
    expect(new Set(statuses.map((s) => s.source_id))).toEqual(new Set(demoSources.map((s) => s.id)));
    for (const s of statuses) {
      expect(s.min_interval_s).toBeGreaterThanOrEqual(60); // never hammer a source
      expect(s.interval_s).toBeGreaterThanOrEqual(s.min_interval_s);
      expect(s.interval_s).toBeLessThanOrEqual(s.max_interval_s);
      expect(Date.parse(s.next_run_at) - Date.parse(s.last_run_at!)).toBe(s.interval_s * 1000);
      if (s.status === "ok") expect(s.errors_in_row).toBe(0);
    }
  });
  it("changes are sorted newest first, within 24 h, from known sources, with valid evidence", () => {
    const { statuses, changes } = buildDemoWatch(ANCHOR);
    const ids = new Set(statuses.map((s) => s.source_id));
    const evidence = new Set(demoEvidence.map((e) => e.id));
    for (let i = 1; i < changes.length; i++) expect(changes[i - 1].ts >= changes[i].ts).toBe(true);
    for (const c of changes) {
      expect(ids.has(c.source_id)).toBe(true);
      expect(ANCHOR - Date.parse(c.ts)).toBeLessThanOrEqual(86_400_000);
      expect(c.summary.length).toBeGreaterThan(0);
      if (c.evidence_id) expect(evidence.has(c.evidence_id)).toBe(true);
    }
    const byKind = new Set(changes.map((c) => c.kind));
    expect(byKind).toEqual(new Set(["quote_change", "layout_change", "status_change"]));
  });
  it("changes_24h matches the generated changes per source", () => {
    const { statuses, changes } = buildDemoWatch(ANCHOR);
    for (const s of statuses) expect(changes.filter((c) => c.source_id === s.source_id).length).toBe(s.changes_24h);
  });
  it("manual poll records a change for readable sources and an error for blocked ones", () => {
    const now = Date.now();
    const before = demoWatchStatuses(now).find((s) => s.source_id === "chaco")!;
    const change = demoTriggerPoll("chaco", now);
    expect(change).not.toBeNull();
    expect(change!.source_id).toBe("chaco");
    expect(change!.data_mode).toBe("demo");
    const after = demoWatchStatuses(now).find((s) => s.source_id === "chaco")!;
    expect(after.last_run_at).toBe(new Date(now).toISOString());
    expect(Date.parse(after.next_run_at)).toBe(now + after.interval_s * 1000);
    expect(after.changes_24h).toBe(before.changes_24h + 1);
    expect(demoChanges(now)[0].id).toBe(change!.id);

    const blockedBefore = demoWatchStatuses(now).find((s) => s.source_id === "revolut")!;
    expect(demoTriggerPoll("revolut", now)).toBeNull();
    const blockedAfter = demoWatchStatuses(now).find((s) => s.source_id === "revolut")!;
    expect(blockedAfter.errors_in_row).toBe(blockedBefore.errors_in_row + 1);
    expect(() => demoTriggerPoll("nope", now)).toThrow();
  });
  it("scheduled polls that came due are advanced so the countdown never stays in the past", () => {
    const later = Date.now() + 3 * 3600 * 1000;
    for (const s of demoWatchStatuses(later)) if (s.enabled) expect(Date.parse(s.next_run_at)).toBeGreaterThan(later);
  });
  it("manual adjustments clamp the interval and reschedule when re-enabled", () => {
    const now = Date.now();
    const s = demoUpdateWatch("chaco", { interval_s: 5 }, now);
    expect(s.interval_s).toBe(s.min_interval_s);
    const off = demoUpdateWatch("chaco", { enabled: false }, now);
    expect(off.enabled).toBe(false);
    const on = demoUpdateWatch("chaco", { enabled: true }, now);
    expect(Date.parse(on.next_run_at)).toBe(now + on.interval_s * 1000);
  });
  it("demo rules and tests never pretend to send anything", () => {
    const rule = demoCreateRule({ name: "t", kind: "cycle_roi", threshold: "0.002", params: null, channel: "telegram", target: "123456789", cooldown_s: 600, enabled: true });
    expect(rule.data_mode).toBe("demo");
    expect(rule.id).toMatch(/^local-/);
    const ev = demoTestRule(rule);
    expect(ev.data_mode).toBe("demo");
    expect(ev.delivered).toBe(false);
    expect(ev.error).toMatch(/demonstração/);
    expect(ev.rule_id).toBe(rule.id);
    for (const e of demoAlertEvents(ANCHOR)) expect(demoAlertRules().some((r) => r.id === e.rule_id)).toBe(true);
  });
});

describe("watchApi (demo)", () => {
  it("updating a rule that does not exist fails with 404 instead of inventing a row", async () => {
    resetDemoWatch();
    const attempt = api.updateRule("demo", "nope", { enabled: false });
    await expect(attempt).rejects.toBeInstanceOf(ApiError);
    await expect(attempt).rejects.toMatchObject({ status: 404 });
    expect(demoAlertRules().some((r) => r.id === "nope")).toBe(false);
  });
  it("polling an unknown source fails with 404 like the backend (LOW-11)", async () => {
    resetDemoWatch();
    const attempt = watchApi.triggerPoll("demo", "nope");
    await expect(attempt).rejects.toBeInstanceOf(ApiError);
    await expect(attempt).rejects.toMatchObject({ status: 404 });
  });
});
