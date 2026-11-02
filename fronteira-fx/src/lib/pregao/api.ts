/**
 * Fetchers do pregão (§0.6, §2.6). Modo `demo` usa os geradores locais e nunca toca a rede;
 * `real` e `simulation` vão ao backend pelo proxy (`API_BASE`, D3: `simulation` leva `?data_mode=simulation`),
 * validam cada resposta com zod e convertem falhas de contrato em `ApiError(0, …)`.
 */
import { z } from "zod";
import { API_BASE, ApiError, modeQuery, type Mode } from "@/lib/api/client";
import { aggregateHistory, tailLimit } from "./candles";
import { demoCandles, demoSessions, demoStats } from "./demo";
import { CandleSeriesSchema, HouseSessionsSchema, SessionStatsListSchema, decStr, isoDate } from "./schemas";
import type { CandleSeries, HouseSession, SessionStats, Timeframe } from "./types";

/** Máximo de chaves por chamada a `/v1/pregao/stats` (D49). */
export const STATS_BATCH = 20;
const DEFAULT_LIMIT = 300;
const HISTORY_GRID_S = 300;

export interface FetchOpts {
  now?: Date;
  signal?: AbortSignal;
}
export interface CandleOpts extends FetchOpts {
  from?: string;
  to?: string;
  limit?: number;
}

const HistorySchema = z.object({
  key: z.string(),
  points: z.array(z.object({ t: isoDate, buy: decStr.nullable(), sell: decStr.nullable(), mid: decStr.nullable() })),
});

function qs(params: Record<string, string | number | undefined>): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined) p.set(k, String(v));
  const s = p.toString();
  return s ? `?${s}` : "";
}

async function getJson<T>(route: string, query: string, schema: z.ZodType<T>, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${API_BASE}${route}${query}`, { headers: { "content-type": "application/json" }, signal });
  if (!res.ok) throw new ApiError(res.status, `${res.status} ${res.statusText} em ${route}`);
  let body: unknown;
  try {
    body = await res.json();
  } catch {
    throw new ApiError(0, `contrato inválido em ${route}: o corpo não é JSON`);
  }
  const parsed = schema.safeParse(body);
  if (!parsed.success) throw new ApiError(0, `contrato inválido em ${route}: ${z.prettifyError(parsed.error)}`);
  return parsed.data;
}

/** Limite de janela em ms; `undefined` ou data inválida → sem limite. */
function boundMs(iso: string | undefined, unbounded: number): number {
  if (iso === undefined) return unbounded;
  const ms = Date.parse(iso);
  return Number.isNaN(ms) ? unbounded : ms;
}

const isNotFound = (e: unknown): boolean => e instanceof ApiError && e.status === 404;

export async function fetchCandles(mode: Mode, key: string, tf: Timeframe, opts: CandleOpts = {}): Promise<CandleSeries> {
  const limit = opts.limit ?? DEFAULT_LIMIT;
  if (mode === "demo") return { key, tf, candles: demoCandles(key, tf, opts.now ?? new Date(), limit), data_mode: "demo" };
  try {
    return await getJson("/v1/candles", qs({ key, tf, from: opts.from, to: opts.to, limit: opts.limit, ...modeQuery(mode) }), CandleSeriesSchema, opts.signal);
  } catch (e) {
    if (!isNotFound(e)) throw e;
  }
  // Router ainda não registrado: agrega o histórico de 5 min localmente (D33), na janela pedida
  // (`from` inclusivo, `to` exclusivo sobre `t`, como §0.4), pois `/v1/history` não recebe janela.
  const history = await getJson("/v1/history", qs({ key, grid: HISTORY_GRID_S, ...modeQuery(mode) }), HistorySchema, opts.signal);
  const fromMs = boundMs(opts.from, Number.NEGATIVE_INFINITY);
  const toMs = boundMs(opts.to, Number.POSITIVE_INFINITY);
  const points = history.points.filter((p) => {
    const t = Date.parse(p.t);
    return t >= fromMs && t < toMs;
  });
  return { key, tf, candles: tailLimit(aggregateHistory(points, tf, mode), limit), data_mode: mode };
}

export async function fetchStats(mode: Mode, keys: string[], opts: FetchOpts = {}): Promise<SessionStats[]> {
  if (keys.length === 0) return [];
  if (mode === "demo") {
    const now = opts.now ?? new Date();
    return keys.map((k) => demoStats(k, now));
  }
  const out: SessionStats[] = [];
  for (let i = 0; i < keys.length; i += STATS_BATCH) {
    const batch = keys.slice(i, i + STATS_BATCH);
    try {
      out.push(...(await getJson("/v1/pregao/stats", qs({ keys: batch.join(","), ...modeQuery(mode) }), SessionStatsListSchema, opts.signal)));
    } catch (e) {
      if (!isNotFound(e)) throw e;
      // 404 no primeiro lote: a rota não existe neste backend, não adianta insistir.
      if (out.length === 0) return [];
      // 404 num lote posterior: mantém os lotes já obtidos.
    }
  }
  return out;
}

export async function fetchSessions(mode: Mode, opts: FetchOpts = {}): Promise<HouseSession[]> {
  if (mode === "demo") return demoSessions(opts.now ?? new Date());
  try {
    return await getJson("/v1/pregao/sessions", qs(modeQuery(mode)), HouseSessionsSchema, opts.signal);
  } catch (e) {
    if (isNotFound(e)) return [];
    throw e;
  }
}
