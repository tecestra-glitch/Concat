/**
 * Módulos `watch` (monitoramento ao vivo de sites sem API) e `notify` (alertas).
 * Mirrors docs/api-contract.md. Like client.ts, every call takes the resolved mode and serves
 * the isolated demo dataset (demo-watch.ts) when mode is "demo"; the demo rows are flagged
 * `data_mode = "demo"` and are never mixed with real data.
 */
import { ApiError, http, modeQuery, qs, type Mode } from "./client";
import type { DataMode } from "./types";
import { formatPercent, parseDecimalPtBR, toNumber } from "../format";
import {
  demoAlertEvents,
  demoAlertRules,
  demoChanges,
  demoCreateRule,
  demoTestRule,
  demoTriggerPoll,
  demoUpdateWatch,
  demoWatchStatuses,
} from "./demo-watch";

// ---------------------------------------------------------------------------------------------
// Types (contract: "Monitoramento ao vivo (módulo watch)" and "Alertas / notificações (módulo notify)")
// ---------------------------------------------------------------------------------------------

export type WatchState = "ok" | "degraded" | "blocked" | "stale" | "error" | "needs_session";
export type ChangeKind = "quote_change" | "layout_change" | "status_change";
export type AlertKind = "cycle_roi" | "quote_move" | "source_down" | "opportunity_new";
export type AlertChannel = "ui" | "telegram" | "webhook" | "email";

export interface WatchStatus {
  source_id: string;
  enabled: boolean;
  interval_s: number;
  min_interval_s: number;
  max_interval_s: number;
  next_run_at: string;
  last_run_at: string | null;
  last_change_at: string | null;
  changes_24h: number;
  errors_in_row: number;
  etag: string | null;
  content_hash: string | null;
  status: WatchState;
  data_mode: DataMode;
}

export interface Change {
  id: string;
  source_id: string;
  ts: string;
  kind: ChangeKind;
  summary: string;
  before: Record<string, unknown>;
  after: Record<string, unknown>;
  evidence_id: string | null;
  data_mode: DataMode;
}

export interface AlertParams {
  pair?: string;
  city?: string | null;
}

export interface AlertRule {
  id: string;
  name: string;
  kind: AlertKind;
  /** Decimal string. Ratio for cycle_roi / quote_move / opportunity_new; seconds for source_down. */
  threshold: string;
  params: AlertParams | null;
  channel: AlertChannel;
  target: string | null;
  cooldown_s: number;
  enabled: boolean;
  data_mode: DataMode;
}

export type AlertRuleInput = Omit<AlertRule, "id" | "data_mode">;

export interface AlertEvent {
  id: string;
  rule_id: string;
  ts: string;
  message: string;
  payload: Record<string, unknown>;
  channel: AlertChannel;
  delivered: boolean;
  error: string | null;
  data_mode: DataMode;
}

export interface WatchPatch {
  interval_s?: number;
  enabled?: boolean;
}

export interface ChangeFilters {
  source?: string;
  from?: string;
  kind?: string;
}

export interface EventFilters {
  from?: string;
  rule?: string;
}

// ---------------------------------------------------------------------------------------------
// Labels
// ---------------------------------------------------------------------------------------------

export const WATCH_STATE_LABEL: Record<WatchState, string> = {
  ok: "ok",
  degraded: "degradada",
  blocked: "bloqueada",
  stale: "antiga",
  error: "erro",
  needs_session: "exige sessão",
};

export const WATCH_STATE_TONE: Record<WatchState, "gain" | "warn" | "loss" | "outline"> = {
  ok: "gain",
  degraded: "warn",
  stale: "warn",
  needs_session: "warn",
  blocked: "loss",
  error: "loss",
};

export const CHANGE_KIND_LABEL: Record<ChangeKind, string> = {
  quote_change: "cotação",
  layout_change: "layout",
  status_change: "estado",
};

export const CHANGE_KIND_TONE: Record<ChangeKind, "accent" | "warn" | "outline"> = {
  quote_change: "accent",
  layout_change: "warn",
  status_change: "outline",
};

export const ALERT_KIND_LABEL: Record<AlertKind, string> = {
  cycle_roi: "ROI de ciclo",
  quote_move: "Movimento de cotação",
  source_down: "Fonte fora do ar",
  opportunity_new: "Nova oportunidade",
};

export const ALERT_CHANNEL_LABEL: Record<AlertChannel, string> = {
  ui: "Interface",
  telegram: "Telegram",
  webhook: "Webhook",
  email: "E-mail",
};

export const ALERT_KINDS: AlertKind[] = ["cycle_roi", "quote_move", "source_down", "opportunity_new"];
export const ALERT_CHANNELS: AlertChannel[] = ["ui", "telegram", "webhook", "email"];
export const ALERT_PAIRS = ["USD/PYG", "BRL/PYG", "USD/BRL"] as const;

// ---------------------------------------------------------------------------------------------
// Pure helpers (unit-tested in src/test/watch.test.ts)
// ---------------------------------------------------------------------------------------------

/** Seconds remaining until `targetIso`, floored at 0; null when the date is invalid. */
export function secondsUntil(targetIso: string | null | undefined, now: number): number | null {
  if (!targetIso) return null;
  const t = new Date(targetIso).getTime();
  if (Number.isNaN(t)) return null;
  return Math.max(0, Math.ceil((t - now) / 1000));
}

/**
 * Countdown for the next poll: "agora" | "42 s" | "2:05" (m:ss) | "1 h 05 min".
 * Designed to tick visibly every second below one hour.
 */
export function formatCountdown(targetIso: string | null | undefined, now: number): string {
  const s = secondsUntil(targetIso, now);
  if (s === null) return "—";
  if (s <= 0) return "agora";
  if (s < 60) return `${s} s`;
  if (s < 3600) {
    const m = Math.floor(s / 60);
    const sec = s % 60;
    return `${m}:${String(sec).padStart(2, "0")}`;
  }
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  return `${h} h ${String(m).padStart(2, "0")} min`;
}

/** Wall-clock time of an ISO timestamp, pt-BR "14:05:32"; "—" when invalid. */
export function formatClock(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return new Intl.DateTimeFormat("pt-BR", { hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(d);
}

/** Interval / cooldown in seconds → "45 s" | "2 min" | "1 min 30 s" | "1 h" | "1 h 30 min". */
export function formatInterval(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds) || seconds < 0) return "—";
  const s = Math.round(seconds);
  if (s < 60) return `${s} s`;
  if (s < 3600) {
    const m = Math.floor(s / 60);
    const rest = s % 60;
    return rest ? `${m} min ${rest} s` : `${m} min`;
  }
  const h = Math.floor(s / 3600);
  const m = Math.round((s % 3600) / 60);
  return m ? `${h} h ${m} min` : `${h} h`;
}

/** Kinds whose threshold is a ratio (shown as pt-BR percent). source_down uses seconds. */
export function isRatioKind(kind: AlertKind): boolean {
  return kind !== "source_down";
}

/** Human form of a stored threshold: ratio → "0,20 %", seconds → "15 min". */
export function formatThreshold(kind: AlertKind, threshold: string | number | null | undefined): string {
  if (isRatioKind(kind)) return formatPercent(threshold);
  const n = toNumber(threshold);
  return n === null ? "—" : formatInterval(n);
}

export type ThresholdValidation = { ok: true; value: string } | { ok: false; error: string };

/**
 * Validates the threshold the user typed for a given kind and converts it to the API form:
 * ratio kinds take a percent (0 < p ≤ 100) and store the ratio ("0,25" → "0.0025");
 * source_down takes minutes (integer ≥ 1) and stores seconds ("15" → "900").
 */
export function validateThreshold(kind: AlertKind, raw: string): ThresholdValidation {
  // pt-BR input ("5.000", "0,25") → canonical decimal string (F7) → number only for the range checks.
  const parsed = parseDecimalPtBR(raw);
  const n = parsed === null ? null : Number(parsed);
  if (isRatioKind(kind)) {
    if (n === null || n <= 0 || n > 100) return { ok: false, error: "Informe um percentual entre 0 e 100 (ex.: 0,25)." };
    // Avoid binary noise: 0.25 / 100 → 0.0025 exactly, as a decimal string.
    const ratio = Math.round(n * 1_000_000) / 100_000_000;
    return { ok: true, value: ratio.toFixed(8).replace(/0+$/, "").replace(/\.$/, "") };
  }
  if (n === null || !Number.isInteger(n) || n < 1 || n > 1440) return { ok: false, error: "Informe minutos inteiros entre 1 e 1440." };
  return { ok: true, value: String(n * 60) };
}

export type TargetValidation = { ok: true; value: string | null } | { ok: false; error: string };

/** The `target` field is required for every channel but the UI, with a format check per channel. */
export function validateTarget(channel: AlertChannel, raw: string): TargetValidation {
  const v = raw.trim();
  if (channel === "ui") return { ok: true, value: null };
  if (!v) return { ok: false, error: "Informe o destino do canal." };
  if (channel === "telegram") return /^(-?\d{5,}|@[A-Za-z0-9_]{5,})$/.test(v) ? { ok: true, value: v } : { ok: false, error: "Use o chat_id numérico ou @canal do Telegram." };
  if (channel === "webhook") return /^https?:\/\/\S+$/i.test(v) ? { ok: true, value: v } : { ok: false, error: "Use uma URL http(s) completa." };
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v) ? { ok: true, value: v } : { ok: false, error: "Use um e-mail válido." };
}

export interface WatchSummary {
  ok: number;
  degraded: number;
  blocked: number;
  enabled: number;
  medianIntervalS: number | null;
}

/** Counts by state (stale/needs_session count as degraded; error counts as blocked) and the median interval of enabled sources. */
export function summarizeWatch(statuses: WatchStatus[]): WatchSummary {
  const out: WatchSummary = { ok: 0, degraded: 0, blocked: 0, enabled: 0, medianIntervalS: null };
  const intervals: number[] = [];
  for (const s of statuses) {
    if (s.status === "ok") out.ok++;
    else if (s.status === "blocked" || s.status === "error") out.blocked++;
    else out.degraded++;
    if (s.enabled) {
      out.enabled++;
      intervals.push(s.interval_s);
    }
  }
  out.medianIntervalS = median(intervals);
  return out;
}

export function median(values: number[]): number | null {
  if (values.length === 0) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

/** Changes whose timestamp is within the last `windowS` seconds of `now`. */
export function countRecent(changes: Change[], now: number, windowS: number): number {
  const from = now - windowS * 1000;
  return changes.filter((c) => {
    const t = new Date(c.ts).getTime();
    return !Number.isNaN(t) && t >= from && t <= now;
  }).length;
}

export function matchesChange(c: Change, f: ChangeFilters): boolean {
  if (f.source && f.source !== "all" && c.source_id !== f.source) return false;
  if (f.kind && f.kind !== "all" && c.kind !== f.kind) return false;
  if (f.from && new Date(c.ts).getTime() < new Date(f.from).getTime()) return false;
  return true;
}

// ---------------------------------------------------------------------------------------------
// Client
// ---------------------------------------------------------------------------------------------

/** `real` and `simulation` go to the backend declaring `?data_mode=` (the instance answers 409 when it serves another mode, SEC-01); only `demo` is local. */
export const watchApi = {
  async statuses(mode: Mode): Promise<WatchStatus[]> {
    if (mode !== "demo") return http<WatchStatus[]>(`/v1/watch/sources${qs(modeQuery(mode))}`);
    return demoWatchStatuses();
  },
  async updateSource(mode: Mode, id: string, patch: WatchPatch): Promise<WatchStatus> {
    if (mode !== "demo") return http<WatchStatus>(`/v1/watch/sources/${encodeURIComponent(id)}${qs(modeQuery(mode))}`, { method: "POST", body: JSON.stringify(patch) });
    return demoUpdateWatch(id, patch);
  },
  /** Sondagem imediata (MCP: trigger_poll). Returns the detected Change, or null when nothing changed. */
  async triggerPoll(mode: Mode, id: string): Promise<Change | null> {
    if (mode !== "demo") return http<Change | null>(`/v1/watch/run/${encodeURIComponent(id)}${qs(modeQuery(mode))}`, { method: "POST" });
    try {
      return demoTriggerPoll(id);
    } catch (err) {
      throw new ApiError(404, err instanceof Error ? err.message : `fonte ${id} não monitorada (demonstração)`);
    }
  },
  async changes(mode: Mode, f: ChangeFilters = {}): Promise<Change[]> {
    if (mode !== "demo") return http<Change[]>(`/v1/watch/changes${qs({ ...f, ...modeQuery(mode) })}`);
    return demoChanges().filter((c) => matchesChange(c, f));
  },
  async rules(mode: Mode): Promise<AlertRule[]> {
    if (mode !== "demo") return http<AlertRule[]>(`/v1/alerts/rules${qs(modeQuery(mode))}`);
    return demoAlertRules();
  },
  async createRule(mode: Mode, input: AlertRuleInput): Promise<AlertRule> {
    if (mode !== "demo") return http<AlertRule>(`/v1/alerts/rules${qs(modeQuery(mode))}`, { method: "POST", body: JSON.stringify(input) });
    return demoCreateRule(input);
  },
  // PATCH/DELETE of a rule live in client.ts (`api.updateRule` / `api.deleteRule`): one client per operation.
  async events(mode: Mode, f: EventFilters = {}): Promise<AlertEvent[]> {
    if (mode !== "demo") return http<AlertEvent[]>(`/v1/alerts/events${qs({ ...f, ...modeQuery(mode) })}`);
    return demoAlertEvents().filter((e) => (!f.rule || f.rule === "all" || e.rule_id === f.rule) && (!f.from || new Date(e.ts).getTime() >= new Date(f.from).getTime()));
  },
  /** Envia mensagem de teste pelo canal da regra. In demo mode nothing is sent; the event says so. */
  async testRule(mode: Mode, rule: AlertRule): Promise<AlertEvent> {
    if (mode !== "demo") return http<AlertEvent>(`/v1/alerts/test/${encodeURIComponent(rule.id)}${qs(modeQuery(mode))}`, { method: "POST" });
    return demoTestRule(rule);
  },
};
