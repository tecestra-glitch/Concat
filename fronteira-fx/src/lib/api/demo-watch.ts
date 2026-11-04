/**
 * DEMONSTRAÇÃO — módulos watch/notify. Dados ilustrativos, nunca misturados com dados reais.
 * Every record carries data_mode = "demo". The generator is seeded (deterministic) and anchored
 * to the current 5-minute bucket so ages and countdowns look realistic; a tiny in-memory store
 * then advances scheduled polls and records manual ones, so the demo behaves like a live backend.
 */
import type { AlertChannel, AlertEvent, AlertRule, AlertRuleInput, Change, ChangeKind, WatchPatch, WatchState, WatchStatus } from "./watch";
import { demoEvidence, demoSources } from "./demo-data";

export const DEMO_WATCH_NOW = Math.floor(Date.now() / 300_000) * 300_000;

function seeded(seed: number) {
  let s = seed >>> 0;
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0;
    return s / 2 ** 32;
  };
}

function hash(str: string): number {
  let h = 2166136261;
  for (let i = 0; i < str.length; i++) h = Math.imul(h ^ str.charCodeAt(i), 16777619);
  return h >>> 0;
}

function hex(str: string): string {
  return hash(str).toString(16).padStart(8, "0").repeat(8);
}

// ---------------------------------------------------------------------------------------------
// Watch statuses
// ---------------------------------------------------------------------------------------------

interface WatchSpec {
  id: string;
  status: WatchState;
  enabled: boolean;
  interval: number;
  min: number;
  max: number;
  lastRunAgo: number;
  lastChangeAgo: number | null;
  changes24h: number;
  errors: number;
}

type WatchOverride = Omit<WatchSpec, "id">;

/** A source without its own row: healthy, polled at the floor of 60 s × 5, one change in the last day. */
const DEFAULT_WATCH: WatchOverride = { status: "ok", enabled: true, interval: 300, min: 60, max: 900, lastRunAgo: 150, lastChangeAgo: 3000, changes24h: 1, errors: 0 };

/** Per-source scheduler state. Intervals reflect the adaptive scheduler: short for lively sources, backed off after errors. */
const WATCH_OVERRIDES: Record<string, WatchOverride> = {
  chaco: { status: "ok", enabled: true, interval: 120, min: 60, max: 900, lastRunAgo: 95, lastChangeAgo: 480, changes24h: 7, errors: 0 },
  alberdi: { status: "ok", enabled: true, interval: 180, min: 60, max: 900, lastRunAgo: 140, lastChangeAgo: 1500, changes24h: 5, errors: 0 },
  norte: { status: "degraded", enabled: true, interval: 600, min: 60, max: 900, lastRunAgo: 420, lastChangeAgo: 3600, changes24h: 1, errors: 2 },
  bonanza: { status: "ok", enabled: true, interval: 300, min: 120, max: 1800, lastRunAgo: 200, lastChangeAgo: 2700, changes24h: 3, errors: 0 },
  bcp: { status: "stale", enabled: true, interval: 3600, min: 900, max: 7200, lastRunAgo: 900, lastChangeAgo: 79200, changes24h: 1, errors: 0 },
  westernunion: { status: "needs_session", enabled: true, interval: 900, min: 300, max: 3600, lastRunAgo: 500, lastChangeAgo: 5400, changes24h: 1, errors: 3 },
  nomad: { status: "ok", enabled: true, interval: 300, min: 60, max: 900, lastRunAgo: 230, lastChangeAgo: 4200, changes24h: 2, errors: 0 },
  revolut: { status: "blocked", enabled: false, interval: 900, min: 300, max: 3600, lastRunAgo: 7200, lastChangeAgo: null, changes24h: 0, errors: 6 },
};

/** One row per demo source — derived from `demoSources`, so adding a source there adds a monitored row here. */
const WATCH_SPECS: WatchSpec[] = demoSources.map((s) => ({ id: s.id, ...(WATCH_OVERRIDES[s.id] ?? DEFAULT_WATCH) }));

interface PriceSpec {
  pair: string;
  city: string | null;
  side: "venda" | "compra" | "referência";
  value: number;
  step: number;
  decimals: number;
}

/** Running price per source used to build "antes → depois" summaries. */
const PRICE_SPECS: Record<string, PriceSpec> = {
  chaco: { pair: "USD/PYG", city: "CDE", side: "venda", value: 7360, step: 10, decimals: 0 },
  alberdi: { pair: "USD/PYG", city: "CDE", side: "venda", value: 7350, step: 10, decimals: 0 },
  norte: { pair: "USD/PYG", city: "ASU", side: "venda", value: 7365, step: 5, decimals: 0 },
  bonanza: { pair: "BRL/PYG", city: "ASU", side: "compra", value: 1345, step: 2, decimals: 0 },
  bcp: { pair: "USD/PYG", city: null, side: "referência", value: 7318.14, step: 3.2, decimals: 2 },
  westernunion: { pair: "BRL/PYG", city: null, side: "venda", value: 1360.8, step: 1.5, decimals: 1 },
  nomad: { pair: "USD/BRL", city: null, side: "venda", value: 5.4187, step: 0.0042, decimals: 4 },
  revolut: { pair: "USD/BRL", city: null, side: "venda", value: 5.41, step: 0.01, decimals: 2 },
};

/** Sources without a price row (none today) fall back to a generic USD/PYG reading so the generator never crashes. */
const DEFAULT_PRICE: PriceSpec = { pair: "USD/PYG", city: null, side: "venda", value: 7350, step: 5, decimals: 0 };

function priceSpec(sourceId: string): PriceSpec {
  return PRICE_SPECS[sourceId] ?? DEFAULT_PRICE;
}

function fmt(n: number, decimals: number): string {
  return n.toFixed(decimals).replace(".", ",");
}

function quoteSummary(sourceId: string, before: number, after: number): string {
  const p = priceSpec(sourceId);
  const where = p.city ? ` ${p.city}` : "";
  return `${p.pair}${where} ${p.side} ${fmt(before, p.decimals)} → ${fmt(after, p.decimals)}`;
}

const STATUS_SUMMARY: Record<string, [string, string]> = {
  norte: ["ok", "degraded — cadeia TLS inválida (verificação falhou)"],
  westernunion: ["ok", "needs_session — simulador exigiu nova sessão"],
  revolut: ["degraded", "blocked — HTTP 403 no conversor público"],
  bcp: ["ok", "stale — referência diária ainda não publicada"],
};

function evidenceFor(sourceId: string, n: number): string | null {
  const list = demoEvidence.filter((e) => e.source_id === sourceId);
  if (list.length === 0) return null;
  return list[n % list.length].id;
}

export interface DemoWatchData {
  statuses: WatchStatus[];
  changes: Change[];
}

/** Pure, deterministic generator: the same anchor always yields the same statuses and changes. */
export function buildDemoWatch(anchor: number = DEMO_WATCH_NOW): DemoWatchData {
  const rnd = seeded(20261102);
  const iso = (offsetS: number) => new Date(anchor + offsetS * 1000).toISOString();
  const statuses: WatchStatus[] = WATCH_SPECS.map((w) => ({
    source_id: w.id,
    enabled: w.enabled,
    interval_s: w.interval,
    min_interval_s: w.min,
    max_interval_s: w.max,
    next_run_at: iso(-w.lastRunAgo + w.interval),
    last_run_at: iso(-w.lastRunAgo),
    last_change_at: w.lastChangeAgo === null ? null : iso(-w.lastChangeAgo),
    changes_24h: w.changes24h,
    errors_in_row: w.errors,
    etag: w.status === "ok" || w.status === "stale" ? `W/"demo-${hash(w.id).toString(16)}"` : null,
    content_hash: w.status === "blocked" || w.status === "needs_session" ? null : hex(`${w.id}:${w.lastRunAgo}`),
    status: w.status,
    data_mode: "demo",
  }));

  const changes: Change[] = [];
  for (const w of WATCH_SPECS) {
    if (w.changes24h === 0 || w.lastChangeAgo === null) continue;
    const price = priceSpec(w.id);
    // Timestamps: the most recent one is exactly last_change_at; the rest spread over the remaining 24 h.
    const offsets = [w.lastChangeAgo];
    for (let i = 1; i < w.changes24h; i++) offsets.push(Math.round(w.lastChangeAgo + rnd() * (86_000 - w.lastChangeAgo)));
    offsets.sort((a, b) => a - b);
    let current = price.value;
    for (let i = 0; i < offsets.length; i++) {
      const isStatus = (w.status !== "ok" && i === 0 && STATUS_SUMMARY[w.id]) || false;
      const isLayout = w.id === "bonanza" && i === offsets.length - 1;
      let kind: ChangeKind = "quote_change";
      let summary: string;
      let before: Record<string, unknown>;
      let after: Record<string, unknown>;
      if (isStatus) {
        kind = "status_change";
        const [b, a] = STATUS_SUMMARY[w.id];
        summary = `estado ${b} → ${a}`;
        before = { status: b };
        after = { status: a.split(" — ")[0] };
      } else if (isLayout) {
        kind = "layout_change";
        summary = "tabela de cotações mudou de seletor (#tabla-cambios → .cotizaciones); parser v2 aplicado";
        before = { selector: "#tabla-cambios" };
        after = { selector: ".cotizaciones" };
      } else {
        const dir = rnd() < 0.5 ? -1 : 1;
        const prev = Number((current - dir * price.step).toFixed(price.decimals));
        summary = quoteSummary(w.id, prev, current);
        before = { [price.side]: fmt(prev, price.decimals) };
        after = { [price.side]: fmt(current, price.decimals) };
        current = prev;
      }
      changes.push({
        id: `demo-ch-${w.id}-${i}`,
        source_id: w.id,
        ts: iso(-offsets[i]),
        kind,
        summary,
        before,
        after,
        evidence_id: kind === "layout_change" ? null : evidenceFor(w.id, i),
        data_mode: "demo",
      });
    }
  }
  changes.sort((a, b) => b.ts.localeCompare(a.ts));
  return { statuses, changes };
}

// ---------------------------------------------------------------------------------------------
// In-memory demo store (advances scheduled polls; records manual ones)
// ---------------------------------------------------------------------------------------------

let store: DemoWatchData | null = null;
let pollCounter = 0;
const liveRnd = seeded(7);
const livePrice: Record<string, number> = {};

function getStore(): DemoWatchData {
  if (!store) {
    store = buildDemoWatch();
    for (const w of WATCH_SPECS) livePrice[w.id] = priceSpec(w.id).value;
  }
  return store;
}

function recordChange(s: WatchStatus, atMs: number, manual: boolean): Change {
  const p = priceSpec(s.source_id);
  const prev = livePrice[s.source_id] ?? p.value;
  const dir = liveRnd() < 0.5 ? -1 : 1;
  const next = Number((prev + dir * p.step).toFixed(p.decimals));
  livePrice[s.source_id] = next;
  const ts = new Date(atMs).toISOString();
  const change: Change = {
    id: `demo-ch-live-${pollCounter}`,
    source_id: s.source_id,
    ts,
    kind: "quote_change",
    summary: `${quoteSummary(s.source_id, prev, next)}${manual ? " (sondagem manual)" : ""}`,
    before: { [p.side]: fmt(prev, p.decimals) },
    after: { [p.side]: fmt(next, p.decimals) },
    evidence_id: evidenceFor(s.source_id, pollCounter),
    data_mode: "demo",
  };
  getStore().changes.unshift(change);
  s.last_change_at = ts;
  s.changes_24h += 1;
  s.content_hash = hex(`${s.source_id}:${atMs}`);
  return change;
}

/** Scheduled polls that came due since the last call are applied, so countdowns restart like a live scheduler. */
function advance(now: number) {
  for (const s of getStore().statuses) {
    if (!s.enabled) continue;
    let next = Date.parse(s.next_run_at);
    if (Number.isNaN(next)) continue;
    let guard = 0;
    while (next <= now && guard++ < 500) {
      pollCounter++;
      s.last_run_at = new Date(next).toISOString();
      if (s.status === "ok" && pollCounter % 3 === 0) recordChange(s, next, false);
      next += s.interval_s * 1000;
    }
    s.next_run_at = new Date(next).toISOString();
  }
}

export function demoWatchStatuses(now: number = Date.now()): WatchStatus[] {
  advance(now);
  return getStore().statuses.map((s) => ({ ...s }));
}

export function demoChanges(now: number = Date.now()): Change[] {
  advance(now);
  return getStore().changes.map((c) => ({ ...c }));
}

/**
 * Manual poll. Sources that cannot be read (blocked / needs_session / error) count one more error
 * and return null; readable sources always yield a change in the demo so the effect is visible.
 */
export function demoTriggerPoll(id: string, now: number = Date.now()): Change | null {
  const s = getStore().statuses.find((x) => x.source_id === id);
  if (!s) throw new Error(`fonte ${id} não monitorada (demo)`);
  pollCounter++;
  s.last_run_at = new Date(now).toISOString();
  s.next_run_at = new Date(now + s.interval_s * 1000).toISOString();
  if (s.status === "blocked" || s.status === "needs_session" || s.status === "error") {
    s.errors_in_row += 1;
    return null;
  }
  s.errors_in_row = 0;
  if (s.status === "stale") s.status = "ok";
  return recordChange(s, now, true);
}

export function demoUpdateWatch(id: string, patch: WatchPatch, now: number = Date.now()): WatchStatus {
  const s = getStore().statuses.find((x) => x.source_id === id);
  if (!s) throw new Error(`fonte ${id} não monitorada (demo)`);
  if (patch.interval_s !== undefined) s.interval_s = Math.min(s.max_interval_s, Math.max(s.min_interval_s, Math.round(patch.interval_s)));
  if (patch.enabled !== undefined && patch.enabled !== s.enabled) {
    s.enabled = patch.enabled;
    if (patch.enabled) s.next_run_at = new Date(now + s.interval_s * 1000).toISOString();
  }
  return { ...s };
}

/** Test hook: rebuilds the watch store and the alert-rule store from the seeded generators. */
export function resetDemoWatch() {
  store = null;
  pollCounter = 0;
  rules = null;
  ruleCounter = 0;
  eventCounter = 0;
}

// ---------------------------------------------------------------------------------------------
// Alerts (notify)
// ---------------------------------------------------------------------------------------------

const RULES: AlertRule[] = [
  { id: "demo-rule-1", name: "Ciclo acima de 0,2 %", kind: "cycle_roi", threshold: "0.002", params: null, channel: "telegram", target: "123456789", cooldown_s: 600, enabled: true, data_mode: "demo" },
  { id: "demo-rule-2", name: "USD/PYG CDE mexeu 0,5 %", kind: "quote_move", threshold: "0.005", params: { pair: "USD/PYG", city: "CDE" }, channel: "ui", target: null, cooldown_s: 300, enabled: true, data_mode: "demo" },
  { id: "demo-rule-3", name: "Fonte fora por 15 min", kind: "source_down", threshold: "900", params: null, channel: "webhook", target: "https://hooks.example.test/fronteira-fx", cooldown_s: 1800, enabled: true, data_mode: "demo" },
  { id: "demo-rule-4", name: "Nova oportunidade ≥ 0,1 %", kind: "opportunity_new", threshold: "0.001", params: null, channel: "email", target: "voce@exemplo.com", cooldown_s: 3600, enabled: false, data_mode: "demo" },
];

interface EventSpec {
  rule: string;
  ago: number;
  message: string;
  channel: AlertChannel;
  delivered: boolean;
  error: string | null;
  payload: Record<string, unknown>;
}

const EVENT_SPECS: EventSpec[] = [
  { rule: "demo-rule-2", ago: 480, message: "USD/PYG CDE (Cambios Chaco) venda 7.350 → 7.360 (+0,14 %) — abaixo do limite acumulado 0,5 % em 1 h: 0,54 %", channel: "ui", delivered: true, error: null, payload: { pair: "USD/PYG", city: "CDE", move: "0.0054" } },
  { rule: "demo-rule-1", ago: 1900, message: "Ciclo BRL@itau → Banco PY PYG → USD → BRL: ROI 0,23 % sobre R$ 5.000 (ganho líquido R$ 11,50)", channel: "telegram", delivered: true, error: null, payload: { roi: "0.0023", capital_brl: "5000" } },
  { rule: "demo-rule-3", ago: 3600, message: "Cambios Norte sem coleta bem-sucedida há 17 min (cadeia TLS inválida)", channel: "webhook", delivered: true, error: null, payload: { source_id: "norte", down_s: 1020 } },
  { rule: "demo-rule-1", ago: 7300, message: "Ciclo BRL@itau → WU → Banco PY PYG → USD → BRL: ROI 0,21 % sobre R$ 10.000", channel: "telegram", delivered: false, error: "Telegram: 429 Too Many Requests (retry em 35 s)", payload: { roi: "0.0021", capital_brl: "10000" } },
  { rule: "demo-rule-3", ago: 20_000, message: "Western Union exigiu nova sessão; 3 falhas seguidas, recuo para 15 min", channel: "webhook", delivered: true, error: null, payload: { source_id: "westernunion", errors_in_row: 3 } },
  { rule: "demo-rule-2", ago: 41_000, message: "USD/PYG CDE (Cambios Alberdi) venda 7.330 → 7.350 (+0,27 %) acumulado 0,52 % em 1 h", channel: "ui", delivered: true, error: null, payload: { pair: "USD/PYG", city: "CDE", move: "0.0052" } },
  { rule: "demo-rule-4", ago: 70_000, message: "Nova oportunidade digital: Nomad USD → Revolut USD, ROI 0,12 % (regra desativada; registrado sem envio)", channel: "email", delivered: false, error: "regra desativada", payload: { roi: "0.0012" } },
];

let ruleCounter = 0;
let eventCounter = 0;

/** Mutable in-memory copy of RULES so create/update/delete behave like a live backend in the demo. */
let rules: AlertRule[] | null = null;

function cloneRule(r: AlertRule): AlertRule {
  return { ...r, params: r.params ? { ...r.params } : null };
}

function getRules(): AlertRule[] {
  if (!rules) rules = RULES.map(cloneRule);
  return rules;
}

export function demoAlertRules(): AlertRule[] {
  return getRules().map(cloneRule);
}

/** PATCH /v1/alerts/rules/{id} (demo). Throws for an unknown id so the caller can surface a 404-like error. */
export function demoUpdateRule(id: string, patch: Partial<AlertRuleInput>): AlertRule {
  const list = getRules();
  const idx = list.findIndex((r) => r.id === id);
  if (idx < 0) throw new Error(`regra ${id} não encontrada (demo)`);
  const next: AlertRule = { ...list[idx], ...patch, id, data_mode: "demo" };
  list[idx] = next;
  return cloneRule(next);
}

/** DELETE /v1/alerts/rules/{id} (demo). Unknown ids are ignored, like a 204 on an already-deleted rule. */
export function demoDeleteRule(id: string): void {
  const list = getRules();
  const idx = list.findIndex((r) => r.id === id);
  if (idx >= 0) list.splice(idx, 1);
}

export function demoAlertEvents(anchor: number = DEMO_WATCH_NOW): AlertEvent[] {
  return EVENT_SPECS.map((e, i) => ({
    id: `demo-ev-${i + 1}`,
    rule_id: e.rule,
    ts: new Date(anchor - e.ago * 1000).toISOString(),
    message: e.message,
    payload: { ...e.payload },
    channel: e.channel,
    delivered: e.delivered,
    error: e.error,
    data_mode: "demo",
  }));
}

/** POST /v1/alerts/rules (demo): mints a flagged record and keeps it in the in-memory store. */
export function demoCreateRule(input: AlertRuleInput): AlertRule {
  ruleCounter++;
  const rule: AlertRule = { ...input, id: `local-rule-${ruleCounter}`, data_mode: "demo" };
  getRules().push(rule);
  return cloneRule(rule);
}

/** Nothing is sent in demo mode; the event states that explicitly instead of faking a delivery. */
export function demoTestRule(rule: AlertRule, now: number = Date.now()): AlertEvent {
  eventCounter++;
  return {
    id: `local-ev-${eventCounter}`,
    rule_id: rule.id,
    ts: new Date(now).toISOString(),
    message: `Teste da regra «${rule.name}» pelo canal ${rule.channel}${rule.target ? ` (${rule.target})` : ""} — demonstração, nada foi enviado.`,
    payload: { test: true, rule_id: rule.id },
    channel: rule.channel,
    delivered: false,
    error: "demonstração — nenhum envio real",
    data_mode: "demo",
  };
}
