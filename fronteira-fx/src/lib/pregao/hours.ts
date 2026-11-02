/**
 * Horários das casas e algoritmo de status de sessão (§0.7). Espelha `services/market_hours.py`.
 * Só Intl: nenhuma dependência de fuso. Toda saída é UTC em ISO 8601.
 */
import type { HouseHours, SessionStatus } from "./types";

export const PRE_OPEN_MIN = 30;

export interface StatusResult {
  status: SessionStatus;
  opens_at: string | null;
  closes_at: string | null;
  next_change_at: string | null;
}

export interface LocalParts {
  year: number;
  month: number;
  day: number;
  isoWeekday: number;
  minutes: number;
}

const NONE: Omit<StatusResult, "status"> = { opens_at: null, closes_at: null, next_change_at: null };
const ALL_DAYS = [1, 2, 3, 4, 5, 6, 7];

export function isAlwaysOpen(hours: HouseHours): boolean {
  return ALL_DAYS.every((d) => hours.days.includes(d)) && hours.opens === "00:00" && hours.closes === "24:00";
}

const formatters = new Map<string, Intl.DateTimeFormat | null>();

/** Formatador por fuso, em cache; `null` quando o Intl rejeita o fuso. */
function formatterFor(tz: string): Intl.DateTimeFormat | null {
  const cached = formatters.get(tz);
  if (cached !== undefined) return cached;
  let f: Intl.DateTimeFormat | null = null;
  try {
    f = new Intl.DateTimeFormat("en-US", {
      timeZone: tz,
      hourCycle: "h23",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      weekday: "short",
    });
  } catch {
    f = null;
  }
  formatters.set(tz, f);
  return f;
}

/** Partes de relógio de parede de `now` no fuso `tz`; `null` se o fuso é inválido. */
export function localParts(now: Date, tz: string): LocalParts | null {
  const f = formatterFor(tz);
  if (f === null || Number.isNaN(now.getTime())) return null;
  const parts = f.formatToParts(now);
  const num = (type: Intl.DateTimeFormatPartTypes): number => Number(parts.find((p) => p.type === type)?.value);
  const year = num("year");
  const month = num("month");
  const day = num("day");
  const hour = num("hour") % 24;
  const minute = num("minute");
  const isoWeekday = ((new Date(Date.UTC(year, month - 1, day)).getUTCDay() + 6) % 7) + 1;
  return { year, month, day, isoWeekday, minutes: hour * 60 + minute };
}

function asUtcMinutes(lp: LocalParts): number {
  return Date.UTC(lp.year, lp.month - 1, lp.day) / 60_000 + lp.minutes;
}

/** Hora local (`hh:mm` do dia `year-month-day`) do fuso `tz` → instante UTC. `hh === 24` = 00:00 do dia seguinte. */
export function zonedToUtc(year: number, month: number, day: number, hh: number, mm: number, tz: string): Date {
  const guess = hh === 24 ? Date.UTC(year, month - 1, day + 1, 0, mm) : Date.UTC(year, month - 1, day, hh, mm);
  // Iteração de ponto fixo: result = guess − offset(result); duas passagens cobrem transições de horário de verão.
  let result = guess;
  for (let i = 0; i < 2; i++) {
    const lp = localParts(new Date(result), tz);
    if (lp === null) return new Date(guess);
    const offsetMin = asUtcMinutes(lp) - result / 60_000;
    result = guess - offsetMin * 60_000;
  }
  return new Date(result);
}

function minutesOf(hhmm: string): number {
  const [h, m] = hhmm.split(":");
  return Number(h) * 60 + Number(m);
}

/** Implementa os passos 1–7 de §0.7. `now` é um instante (UTC). */
export function houseStatus(hours: HouseHours | null | undefined, now: Date): StatusResult {
  if (!hours) return { status: "unknown", ...NONE };
  const lp = localParts(now, hours.tz);
  if (lp === null) return { status: "unknown", ...NONE };
  if (isAlwaysOpen(hours)) return { status: "open", ...NONE };

  const op = minutesOf(hours.opens);
  const cl = minutesOf(hours.closes);
  const [opH, opM] = [Math.floor(op / 60), op % 60];
  const [clH, clM] = [Math.floor(cl / 60), cl % 60];
  const { isoWeekday: wd, minutes: m } = lp;
  const times = (dayOffset: number) => ({
    opens_at: zonedToUtc(lp.year, lp.month, lp.day + dayOffset, opH, opM, hours.tz),
    closes_at: zonedToUtc(lp.year, lp.month, lp.day + dayOffset, clH, clM, hours.tz),
  });

  if (hours.days.includes(wd)) {
    if (op <= m && m < cl) {
      const t = times(0);
      return { status: "open", opens_at: t.opens_at.toISOString(), closes_at: t.closes_at.toISOString(), next_change_at: t.closes_at.toISOString() };
    }
    if (op - PRE_OPEN_MIN <= m && m < op) {
      const t = times(0);
      return { status: "pre", opens_at: t.opens_at.toISOString(), closes_at: t.closes_at.toISOString(), next_change_at: t.opens_at.toISOString() };
    }
  }

  const first = m < op - PRE_OPEN_MIN ? 0 : 1;
  for (let d = first; d <= 8; d++) {
    if (!hours.days.includes(((wd - 1 + d) % 7) + 1)) continue;
    const t = times(d);
    return {
      status: "closed",
      opens_at: t.opens_at.toISOString(),
      closes_at: t.closes_at.toISOString(),
      next_change_at: new Date(t.opens_at.getTime() - PRE_OPEN_MIN * 60_000).toISOString(),
    };
  }
  return { status: "closed", ...NONE };
}
