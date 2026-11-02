/**
 * Derivação no cliente (§0.11): funções puras que transformam `Quote[]` nos tipos do pregão.
 * Nenhum arredondamento; percentuais são `number | null` já ×100. BCP/dolarPy são referência
 * (`kind: market_reference`): ficam fora dos lados Compra/Venda e nunca recebem ágio.
 */
import type { Quote, Source } from "@/lib/api/types";
import { historyKey } from "@/lib/api/demo-data";
import { toNumber } from "@/lib/format";
import { midOf, pairKeyOf } from "./candles";
import { PAIRS, type BookLevel, type HeatCell, type HouseSession, type PairKey, type Print, type SessionStats, type SessionStatus, type TickerItem, type WatchlistRow } from "./types";

const REF_MAX_AGE_MS = 24 * 3600 * 1000;

export function isIncomplete(q: Pick<Quote, "buy" | "sell">): boolean {
  return q.buy === null || q.sell === null;
}

/** `(sell − buy) / mid · 100`; `null` sem um dos lados ou com `mid ≤ 0`. */
export function spreadPct(buy: string | null, sell: string | null): number | null {
  const b = toNumber(buy);
  const s = toNumber(sell);
  if (b === null || s === null) return null;
  const mid = (b + s) / 2;
  return mid <= 0 ? null : ((s - b) / mid) * 100;
}

/** `(rate / refMid − 1) · 100`; `null` quando o lado ou a referência falta. */
export function agioPct(rate: string | null, refMid: number | null): number | null {
  const r = toNumber(rate);
  if (r === null || refMid === null || refMid === 0) return null;
  return ((r - refMid) / refMid) * 100;
}

/** `(curr / prev − 1) · 100`, calculado como `(curr − prev) / prev · 100` para evitar ruído de ponto flutuante; `null` se `prev` é nulo ou zero ou `curr` é nulo. */
export function pctChange(prev: number | null, curr: number | null): number | null {
  if (prev === null || prev === 0 || curr === null) return null;
  return ((curr - prev) / prev) * 100;
}

export function houseName(sources: Source[], sourceId: string): string {
  return sources.find((s) => s.id === sourceId)?.name ?? sourceId;
}

function stripDemo(id: string): string {
  return id.startsWith("demo-") ? id.slice(5) : id;
}

/** `"unknown"` quando a fonte não está em `sessions`; casa `demo-chaco` com `chaco`. */
export function statusOf(sessions: HouseSession[], sourceId: string): SessionStatus {
  const exact = sessions.find((s) => s.source_id === sourceId);
  if (exact) return exact.status;
  const bare = stripDemo(sourceId);
  return sessions.find((s) => stripDemo(s.source_id) === bare)?.status ?? "unknown";
}

const REF_PRIORITY: Record<string, number> = { bcp: 0, dolarpy: 1 };

/**
 * `mid` da referência mais recente do par (bcp antes de dolarpy); `null` se não existe ou se
 * tem mais de 24 h ("sem referência").
 */
export function refMidFor(quotes: Quote[], pair: PairKey, now: Date): number | null {
  const freshAfter = now.getTime() - REF_MAX_AGE_MS;
  let best: Quote | null = null;
  let bestAt = Number.NaN;
  let bestRank = Number.POSITIVE_INFINITY;
  for (const q of quotes) {
    if (q.kind !== "market_reference" || pairKeyOf(historyKey(q)) !== pair) continue;
    const at = Date.parse(q.captured_at);
    // Referência velha não conta: uma `bcp` de ontem não esconde uma `dolarpy` de agora.
    if (Number.isNaN(at) || at < freshAfter) continue;
    const rank = REF_PRIORITY[stripDemo(q.source_id)] ?? 2;
    if (rank < bestRank || (rank === bestRank && at > bestAt)) {
      best = q;
      bestAt = at;
      bestRank = rank;
    }
  }
  return best === null ? null : midOf(best.buy, best.sell);
}

/** Cotação mais recente por chave, só de pares conhecidos. */
function latestByKey(quotes: Quote[], pair?: PairKey): Map<string, { q: Quote; pair: PairKey }> {
  const out = new Map<string, { q: Quote; pair: PairKey }>();
  for (const q of quotes) {
    const key = historyKey(q);
    const p = pairKeyOf(key);
    if (p === null || (pair !== undefined && p !== pair)) continue;
    const cur = out.get(key);
    if (!cur || Date.parse(q.captured_at) > Date.parse(cur.q.captured_at)) out.set(key, { q, pair: p });
  }
  return out;
}

const byCapturedDesc = (a: { captured_at: string }, b: { captured_at: string }) => Date.parse(b.captured_at) - Date.parse(a.captured_at);
const isRef = (x: { kind: Quote["kind"] }) => x.kind === "market_reference";

export function toBookLevels(quotes: Quote[], pair: PairKey, sources: Source[], sessions: HouseSession[], now: Date): BookLevel[] {
  const refMid = refMidFor(quotes, pair, now);
  const levels: BookLevel[] = [];
  for (const [key, { q }] of latestByKey(quotes, pair)) {
    const ref = isRef(q);
    levels.push({
      key,
      pair,
      source_id: q.source_id,
      house: houseName(sources, q.source_id),
      city: q.city,
      channel: q.channel,
      kind: q.kind,
      buy: q.buy,
      sell: q.sell,
      spread_pct: spreadPct(q.buy, q.sell),
      agio_buy_pct: ref ? null : agioPct(q.buy, refMid),
      agio_sell_pct: ref ? null : agioPct(q.sell, refMid),
      status: statusOf(sessions, q.source_id),
      incomplete: isIncomplete(q),
      captured_at: q.captured_at,
      data_mode: q.data_mode,
    });
  }
  const houses = levels.filter((l) => !isRef(l)).sort(byCapturedDesc);
  const refs = levels.filter(isRef).sort(byCapturedDesc);
  return [...houses, ...refs];
}

export function toTickerItems(quotes: Quote[], sources: Source[], statsByKey: ReadonlyMap<string, SessionStats>): TickerItem[] {
  const items: TickerItem[] = [];
  for (const [key, { q, pair }] of latestByKey(quotes)) {
    items.push({
      key,
      pair,
      source_id: q.source_id,
      house: houseName(sources, q.source_id),
      city: q.city,
      kind: q.kind,
      buy: q.buy,
      sell: q.sell,
      mid: midOf(q.buy, q.sell),
      change_pct: toNumber(statsByKey.get(key)?.change_pct ?? null),
      captured_at: q.captured_at,
      incomplete: isIncomplete(q),
      data_mode: q.data_mode,
    });
  }
  return items.sort((a, b) => {
    const dp = PAIRS.indexOf(a.pair) - PAIRS.indexOf(b.pair);
    if (dp !== 0) return dp;
    const dr = Number(isRef(a)) - Number(isRef(b));
    if (dr !== 0) return dr;
    return a.source_id < b.source_id ? -1 : a.source_id > b.source_id ? 1 : 0;
  });
}

export function toWatchlistRows(levels: BookLevel[], statsByKey: ReadonlyMap<string, SessionStats>, sparks: Record<string, number[]>): WatchlistRow[] {
  return levels.map((l) => ({ ...l, change_pct: toNumber(statsByKey.get(l.key)?.change_pct ?? null), spark: sparks[l.key] ?? [] }));
}

export function toHeatCells(levels: BookLevel[]): HeatCell[] {
  return levels
    .filter((l) => !isRef(l))
    .map((l) => ({ key: l.key, pair: l.pair, source_id: l.source_id, house: l.house, spread_pct: l.spread_pct, status: l.status, captured_at: l.captured_at }));
}

/** `null` quando o par da cotação não está em `PAIRS`. */
export function quoteToPrint(q: Quote, prev: Quote | null, house: string): Print | null {
  const key = historyKey(q);
  const pair = pairKeyOf(key);
  if (pair === null) return null;
  const mid = midOf(q.buy, q.sell);
  const prev_mid = prev ? midOf(prev.buy, prev.sell) : null;
  return {
    id: q.id,
    key,
    pair,
    source_id: q.source_id,
    house,
    city: q.city,
    kind: q.kind,
    buy: q.buy,
    sell: q.sell,
    mid,
    prev_mid,
    change_pct: pctChange(prev_mid, mid),
    captured_at: q.captured_at,
    incomplete: isIncomplete(q),
    data_mode: q.data_mode,
  };
}

/** Primeira casa aberta; senão a primeira casa; senão `null`. Referências nunca. */
export function defaultKeyFor(levels: BookLevel[]): string | null {
  const houses = levels.filter((l) => !isRef(l));
  return houses.find((l) => l.status === "open")?.key ?? houses[0]?.key ?? null;
}
