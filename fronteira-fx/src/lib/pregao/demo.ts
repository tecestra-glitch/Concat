/**
 * DEMONSTRAÇÃO — gerador determinístico do pregão (§0.9). Espelha `services/candles_demo.py`
 * (mesma estrutura e constantes; os valores não precisam coincidir bit a bit).
 * `now` é sempre parâmetro: este arquivo não lê o relógio. Todo registro leva `data_mode: "demo"`.
 */
import type { Quote } from "@/lib/api/types";
import { allDemoQuotes, demoSources } from "@/lib/api/demo-data";
import { toNumber } from "@/lib/format";
import { bucketStart, pairKeyOf, pairOf, toDecStr } from "./candles";
import { houseName, quoteToPrint, toBookLevels, toHeatCells, toTickerItems, toWatchlistRows } from "./derive";
import { houseStatus, localParts, zonedToUtc } from "./hours";
import { quoteKey } from "./keys";
import { PAIRS, TF_SECONDS, type BookLevel, type Candle, type HeatCell, type HouseHours, type HouseSession, type PairKey, type Print, type SessionStats, type TickerItem, type Timeframe, type WatchlistRow } from "./types";

export const DEMO_ANCHOR: Record<PairKey, number> = { "USD/PYG": 5940, "USD/BRL": 5.43, "BRL/PYG": 1100 };
export const DEMO_VOL: Record<Timeframe, number> = { "15m": 0.0015, "1h": 0.003, "4h": 0.006, "1d": 0.012 };
export const DEFAULT_SERIES_KEY = "chaco:CDE:USD/PYG:cash:@chaco-cde-centro";

export interface DemoHouse {
  id: string;
  name: string;
  city: "CDE" | "ASU" | null;
  channel: "physical" | "digital";
  reference: boolean;
  pairs: PairKey[];
}

/** Casas do pregão demo, em sequência fixa (§0.9). Nomes iguais aos de `demoSources`. */
export const DEMO_HOUSES: readonly DemoHouse[] = [
  { id: "chaco", name: "Cambios Chaco", city: "CDE", channel: "physical", reference: false, pairs: ["USD/PYG", "BRL/PYG"] },
  { id: "alberdi", name: "Cambios Alberdi", city: "CDE", channel: "physical", reference: false, pairs: ["USD/PYG", "BRL/PYG"] },
  { id: "norte", name: "Cambios Norte", city: "ASU", channel: "physical", reference: false, pairs: ["USD/PYG"] },
  { id: "bonanza", name: "Bonanza Cambios", city: "ASU", channel: "physical", reference: false, pairs: ["USD/PYG", "BRL/PYG"] },
  { id: "nomad", name: "Nomad", city: null, channel: "digital", reference: false, pairs: ["USD/BRL"] },
  { id: "bcp", name: "BCP (referência)", city: null, channel: "digital", reference: true, pairs: ["USD/PYG", "BRL/PYG"] },
];

/**
 * Mesmo conteúdo de `data/market_hours.json` (§0.7) para as casas de `DEMO_HOUSES` que têm horário.
 * alberdi, norte e bonanza não têm horário verificado: ficam sem entrada (status "sem horário").
 */
export const DEMO_HOURS: Record<string, HouseHours> = {
  chaco: {
    name: "Cambios Chaco", city: "CDE", channel: "physical", tz: "America/Asuncion",
    days: [1, 2, 3, 4, 5], opens: "07:15", closes: "16:00",
    schedule: [{ days: [6], opens: "07:15", closes: "13:00" }],
    verified: true, source_url: "https://www.cambioschaco.com.py/en/sucursales/", checked_at: "2026-11-04",
  },
  bcp: {
    name: "BCP (referência)", city: null, channel: "digital", tz: "America/Asuncion",
    days: [1, 2, 3, 4, 5], opens: "08:30", closes: "13:00",
    verified: true, source_url: "https://www.bcp.gov.py/webapps/web/cotizacion/monedas", checked_at: "2026-11-04",
  },
};

/** Filtro de `demoQuotesAt` (D37): só cotações das casas do pregão demo. */
export const DEMO_HOUSE_IDS: ReadonlySet<string> = new Set(DEMO_HOUSES.map((h) => h.id));

const WEEK_S = 604_800;
const ASUNCION = "America/Asuncion";
const SPREAD_FRAC = 0.006;

/** FNV-1a 32 bits sobre os code units da string (`charCodeAt`), como `hash` em `demo-data.ts`. */
export function fnv1a(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619);
  return h >>> 0;
}

/** LCG `s = (s · 1664525 + 1013904223) mod 2^32`; cada chamada devolve o próximo valor em `[0, 1)`. */
export function lcg(seed: number): () => number {
  let s = seed >>> 0;
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0;
    return s / 2 ** 32;
  };
}

/** Ciclo semanal de ±0,4 % sobre a âncora. */
export function drift(i: number, gridS: number): number {
  const sec = i * gridS;
  const phase = ((sec % WEEK_S) + WEEK_S) % WEEK_S;
  return 1 + 0.004 * Math.sin((2 * Math.PI * phase) / WEEK_S);
}

function anchorOf(key: string): number {
  return (DEMO_ANCHOR as Record<string, number>)[pairOf(key)] ?? 1;
}

function seedOf(key: string, tf: Timeframe, i: number): number {
  return fnv1a(`${key}:${tf}:${i}`);
}

export function demoClose(key: string, tf: Timeframe, i: number): number {
  const u1 = lcg(seedOf(key, tf, i))();
  return anchorOf(key) * drift(i, TF_SECONDS[tf]) * (1 + (u1 - 0.5) * DEMO_VOL[tf]);
}

export function demoCandle(key: string, tf: Timeframe, i: number): Candle {
  const g = TF_SECONDS[tf];
  const vol = DEMO_VOL[tf];
  const r = lcg(seedOf(key, tf, i));
  const u1 = r();
  const u2 = r();
  const u3 = r();
  const u4 = r();
  const level = anchorOf(key) * drift(i, g);
  const o = demoClose(key, tf, i - 1);
  const c = level * (1 + (u1 - 0.5) * vol);
  const h = Math.max(o, c) * (1 + (u2 * vol) / 2);
  const l = Math.min(o, c) * (1 - (u3 * vol) / 2);
  const spread = level * SPREAD_FRAC;
  return {
    t: new Date(i * g * 1000).toISOString(),
    o: toDecStr(o, 4),
    h: toDecStr(h, 4),
    l: toDecStr(l, 4),
    c: toDecStr(c, 4),
    n: 1 + Math.floor(u4 * 12),
    spread_avg: toDecStr(spread, 4),
    buy_c: toDecStr(c - spread / 2, 4),
    sell_c: toDecStr(c + spread / 2, 4),
    data_mode: "demo",
  };
}

function isPhysicalKey(key: string): boolean {
  return (key.split(":")[1] ?? "") !== "digital";
}

/**
 * Velas terminando em `bucketStart(now)` inclusive, ascendentes, exatamente `count` emitidas.
 * Buckets de domingo UTC são omitidos (e não contados) para chaves presenciais.
 */
export function demoCandles(key: string, tf: Timeframe, now: Date, count = 300): Candle[] {
  const g = TF_SECONDS[tf];
  const physical = isPhysicalKey(key);
  const out: Candle[] = [];
  let i = Math.round(bucketStart(now.getTime(), g) / (g * 1000));
  while (out.length < count) {
    if (!(physical && new Date(i * g * 1000).getUTCDay() === 0)) out.push(demoCandle(key, tf, i));
    i -= 1;
  }
  return out.reverse();
}

/** 00:00 de Assunção do dia local que contém `now`, como instante UTC. */
export function dayStartAsuncion(now: Date): Date {
  const lp = localParts(now, ASUNCION);
  if (lp === null) return new Date(bucketStart(now.getTime(), 86400));
  return zonedToUtc(lp.year, lp.month, lp.day, 0, 0, ASUNCION);
}

const pad = (n: number, w = 2) => String(n).padStart(w, "0");

/** ISO 8601 com offset do fuso (`2026-11-02T00:00:00-03:00`), como o backend serializa `day_start`. */
function isoWithOffset(d: Date, tz: string): string {
  const lp = localParts(d, tz);
  if (lp === null) return d.toISOString();
  const offsetMin = Math.round(Date.UTC(lp.year, lp.month - 1, lp.day) / 60_000 + lp.minutes - d.getTime() / 60_000);
  const sign = offsetMin < 0 ? "-" : "+";
  const abs = Math.abs(offsetMin);
  const hh = Math.floor(lp.minutes / 60);
  const mm = lp.minutes % 60;
  return `${pad(lp.year, 4)}-${pad(lp.month)}-${pad(lp.day)}T${pad(hh)}:${pad(mm)}:${pad(d.getUTCSeconds())}${sign}${pad(Math.floor(abs / 60))}:${pad(abs % 60)}`;
}

/** Resumo do dia local a partir das velas de 15 min (§0.9). */
export function demoStats(key: string, now: Date): SessionStats {
  const g = TF_SECONDS["15m"];
  const dayStart = dayStartAsuncion(now);
  const day = demoCandles(key, "15m", now, 96).filter((c) => Date.parse(c.t) >= dayStart.getTime());
  const empty: SessionStats = {
    key,
    day_start: isoWithOffset(dayStart, ASUNCION),
    open: null,
    high: null,
    low: null,
    last: null,
    last_at: null,
    change_abs: null,
    change_pct: null,
    n_quotes: 0,
    spread_avg: null,
    houses: 0,
    data_mode: "demo",
  };
  const first = day[0];
  const last = day.at(-1);
  if (!first || !last) return empty;
  const pair = pairKeyOf(key);
  let high = -Infinity;
  let low = Infinity;
  let n = 0;
  let spreadSum = 0;
  let spreadN = 0;
  for (const c of day) {
    high = Math.max(high, toNumber(c.h) ?? -Infinity);
    low = Math.min(low, toNumber(c.l) ?? Infinity);
    n += c.n;
    const s = toNumber(c.spread_avg);
    if (s !== null) {
      spreadSum += s;
      spreadN += 1;
    }
  }
  const open = toNumber(first.o);
  const close = toNumber(last.c);
  const changeAbs = open !== null && close !== null ? close - open : null;
  return {
    ...empty,
    open: first.o,
    high: toDecStr(high, 4),
    low: toDecStr(low, 4),
    last: last.c,
    last_at: new Date(Date.parse(last.t) + g * 1000 - 1000).toISOString(),
    change_abs: changeAbs === null ? null : toDecStr(changeAbs, 8),
    change_pct: changeAbs === null || open === null || open === 0 ? null : toDecStr((changeAbs / open) * 100, 8),
    n_quotes: n,
    spread_avg: spreadN > 0 ? toDecStr(spreadSum / spreadN, 8) : null,
    houses: pair === null ? 0 : DEMO_HOUSES.filter((h) => !h.reference && h.pairs.includes(pair)).length,
  };
}

/** Uma `HouseSession` por casa demo, com status por `houseStatus(DEMO_HOURS[id], now)`. */
export function demoSessions(now: Date): HouseSession[] {
  return DEMO_HOUSES.map((h) => {
    const hours = DEMO_HOURS[h.id];
    const st = houseStatus(hours, now);
    return {
      source_id: `demo-${h.id}`,
      name: h.name,
      city: h.city,
      tz: hours?.tz ?? null,
      channel: h.channel,
      reference: h.reference,
      status: st.status,
      opens_at: st.opens_at,
      closes_at: st.closes_at,
      next_change_at: st.next_change_at,
      data_mode: "demo",
    };
  });
}

/** Cotações base do pregão demo (sem `westernunion` e `revolut`), na sequência de `allDemoQuotes`. */
const demoHouseQuotes: readonly Quote[] = allDemoQuotes.filter((q) => DEMO_HOUSE_IDS.has(q.source_id));

/** Chaves das casas demo (sem referência) que publicam esse par, na sequência das cotações. */
export function demoSeriesKeys(pair: PairKey): string[] {
  const keys: string[] = [];
  for (const q of demoHouseQuotes) {
    const key = quoteKey(q);
    if (q.kind === "market_reference" || pairKeyOf(key) !== pair || keys.includes(key)) continue;
    keys.push(key);
  }
  return keys;
}

/** Cotações demo recarimbadas com idade determinística entre 30 s e 9,5 min antes de `now` (§0.9, D37). */
export function demoQuotesAt(now: Date): Quote[] {
  const base = bucketStart(now.getTime(), 60);
  return demoHouseQuotes.map((q) => ({
    ...q,
    captured_at: new Date(base - ((fnv1a(quoteKey(q)) % 540) + 30) * 1000).toISOString(),
    data_mode: "demo",
  }));
}

function statsByKeyFor(keys: Iterable<string>, now: Date): Map<string, SessionStats> {
  const out = new Map<string, SessionStats>();
  for (const key of keys) if (!out.has(key)) out.set(key, demoStats(key, now));
  return out;
}

export function demoBook(pair: PairKey, now: Date): BookLevel[] {
  return toBookLevels(demoQuotesAt(now), pair, demoSources, demoSessions(now), now);
}

export function demoTicker(now: Date): TickerItem[] {
  const quotes = demoQuotesAt(now);
  return toTickerItems(quotes, demoSources, statsByKeyFor(quotes.map(quoteKey), now));
}

/** Atualizações demo: uma cotação recarimbada a cada 47 s, da mais nova para a mais antiga (§0.9). */
export function demoPrints(now: Date, limit = 20): Print[] {
  const houseQuotes = demoQuotesAt(now).filter((q) => q.kind !== "market_reference");
  if (houseQuotes.length === 0 || limit < 1) return [];
  const base = bucketStart(now.getTime(), 60);
  const stamped: Quote[] = [];
  for (let k = 0; k < limit; k++) {
    const q = houseQuotes[k % houseQuotes.length];
    const key = quoteKey(q);
    const t = base - k * 47_000;
    const minute = Math.floor(t / 60_000);
    const u = lcg(fnv1a(`${key}:print:${minute}`))();
    const factor = 1 + (u - 0.5) * 0.002;
    const dec = q.quote === "PYG" ? 0 : 4;
    const scale = (side: string | null) => {
      const n = toNumber(side);
      return n === null ? null : toDecStr(n * factor, dec);
    };
    stamped.push({ ...q, id: `demo-print-${key}-${minute}`, buy: scale(q.buy), sell: scale(q.sell), captured_at: new Date(t).toISOString() });
  }
  const out: Print[] = [];
  for (let k = 0; k < stamped.length; k++) {
    const q = stamped[k];
    const key = quoteKey(q);
    const prev = stamped.slice(k + 1).find((p) => quoteKey(p) === key) ?? null;
    const print = quoteToPrint(q, prev, houseName(demoSources, q.source_id));
    if (print) out.push(print);
  }
  return out;
}

export function demoWatchlist(pair: PairKey, now: Date): WatchlistRow[] {
  const levels = demoBook(pair, now);
  const keys = levels.map((l) => l.key);
  const sparks: Record<string, number[]> = {};
  for (const key of keys) sparks[key] = demoCandles(key, "1h", now, 24).map((c) => toNumber(c.c) ?? 0);
  return toWatchlistRows(levels, statsByKeyFor(keys, now), sparks);
}

export function demoHeat(now: Date): HeatCell[] {
  return toHeatCells(PAIRS.flatMap((p) => demoBook(p, now)));
}
