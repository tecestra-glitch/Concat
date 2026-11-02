/**
 * Pure helpers that apply live data (snapshot, SSE events) to the TanStack Query cache.
 *
 * Rules (plan F6):
 * - a snapshot only fills queries that are already active (`["quotes", mode, filters]`,
 *   `["sources", mode]`, `["opportunities", mode, filters]`); it never creates keys;
 * - `quote.updated` is written only into quote queries whose filters match the quote
 *   (source / city / pair / modality / amount) and that belong to the same data mode;
 * - modes never mix: a payload stamped with another `data_mode` is ignored.
 */
import type { QueryClient } from "@tanstack/react-query";
import { type ParsedStreamEvent, StreamEventSchema } from "./api/schemas";
import type { Mode, Opportunity, OpportunityFilters, Quote, QuoteFilters, Snapshot, Source } from "./api/types";
import { toNumber } from "./format";

const active = (v: unknown): boolean => v !== undefined && v !== null && v !== "" && v !== "all";

/** Does `q` belong in a quote list filtered by `f`? `city: "digital"` means a quote without city. */
export function quoteMatchesFilters(q: Quote, f?: QuoteFilters): boolean {
  if (!f) return true;
  if (active(f.city)) {
    if (f.city === "digital") {
      if (q.city !== null) return false;
    } else if (q.city !== f.city) return false;
  }
  if (active(f.base) && q.base !== f.base) return false;
  if (active(f.quote) && q.quote !== f.quote) return false;
  if (active(f.source) && q.source_id !== f.source) return false;
  if (active(f.modality) && q.modality !== f.modality) return false;
  if (active(f.amount)) {
    const want = toNumber(f.amount);
    const have = toNumber(q.amount_base);
    if (want === null || have === null || want !== have) return false;
  }
  return true;
}

function opportunityMatchesFilters(o: Opportunity, f: OpportunityFilters | number | undefined): boolean {
  if (f === undefined || f === null) return true;
  const filters: OpportunityFilters = typeof f === "number" ? { capital: f } : f;
  if (active(filters.capital)) {
    const want = toNumber(filters.capital);
    const have = toNumber(o.capital_brl);
    if (want !== null && have !== null && want !== have) return false;
  }
  if (active(filters.channel) && o.channel !== filters.channel) return false;
  if (active(filters.city)) {
    if (filters.city === "digital") {
      if (o.city !== null) return false;
    } else if (o.city !== filters.city) return false;
  }
  return true;
}

/** Replace the quote of the same series (by `series_key`), or append a new series. */
export function mergeQuote(list: Quote[] | undefined, q: Quote): Quote[] {
  if (!list) return [q];
  const idx = list.findIndex((x) => x.series_key === q.series_key);
  if (idx === -1) return [...list, q];
  const next = list.slice();
  next[idx] = q;
  return next;
}

function filtersOf<T>(queryKey: readonly unknown[]): T | undefined | null {
  // key shape: [name, mode, filters?]; anything else (e.g. a string) is not a filtered list.
  const f = queryKey[2];
  if (f === undefined || f === null) return undefined;
  if (typeof f === "number") return f as unknown as T;
  if (typeof f !== "object") return null;
  return f as T;
}

/**
 * Write a `quote.updated` payload into the matching quote lists of `mode` and invalidate its series.
 * A list that is still loading (no data yet) is left alone: seeding it with one quote would make a
 * single row pass for the whole list until the fetch lands.
 */
export function applyQuoteUpdate(qc: QueryClient, mode: Mode, q: Quote): void {
  if (q.data_mode && q.data_mode !== mode) return;
  for (const query of qc.getQueryCache().findAll({ queryKey: ["quotes", mode] })) {
    const f = filtersOf<QuoteFilters>(query.queryKey);
    if (f === null) continue;
    if (!quoteMatchesFilters(q, f)) continue;
    qc.setQueryData<Quote[]>(query.queryKey, (old) => (old === undefined ? old : mergeQuote(old, q)));
  }
  void qc.invalidateQueries({ queryKey: ["history", mode, q.series_key] });
  void qc.invalidateQueries({ queryKey: ["volatility", mode, q.series_key] });
}

/** Fill the active queries of `mode` from a snapshot; never creates new keys. */
export function applySnapshot(qc: QueryClient, mode: Mode, snap: Snapshot): void {
  if (snap.data_mode && snap.data_mode !== mode) return;
  const cache = qc.getQueryCache();
  for (const query of cache.findAll({ queryKey: ["quotes", mode] })) {
    const f = filtersOf<QuoteFilters>(query.queryKey);
    if (f === null) continue;
    qc.setQueryData<Quote[]>(
      query.queryKey,
      snap.quotes.filter((q) => (!q.data_mode || q.data_mode === mode) && quoteMatchesFilters(q, f)),
    );
  }
  if (cache.find({ queryKey: ["sources", mode], exact: true })) {
    qc.setQueryData<Source[]>(["sources", mode], snap.sources);
  }
  for (const query of cache.findAll({ queryKey: ["opportunities", mode] })) {
    const f = filtersOf<OpportunityFilters | number>(query.queryKey);
    if (f === null) continue;
    qc.setQueryData<Opportunity[]>(
      query.queryKey,
      snap.opportunities.filter((o) => (!o.data_mode || o.data_mode === mode) && opportunityMatchesFilters(o, f)),
    );
  }
}

/** Update one source inside the active `["sources", mode]` list (no-op when the list is not loaded). */
export function applySourceHealth(qc: QueryClient, mode: Mode, s: Source): void {
  if (s.data_mode && s.data_mode !== mode) return;
  if (!qc.getQueryCache().find({ queryKey: ["sources", mode], exact: true })) return;
  qc.setQueryData<Source[]>(["sources", mode], (old) => (old ? old.map((x) => (x.id === s.id ? s : x)) : old));
}

/**
 * Parse one SSE frame. The body's own `id` wins; when it is missing, empty or null the SSE `id:`
 * line (`MessageEvent.lastEventId`) is used, so replay dedupe and the cursor keep working.
 * Malformed JSON, an unknown event type or a frame with no id at all yields `null`.
 */
export function parseStreamFrame(data: string, lastEventId: string): ParsedStreamEvent | null {
  let raw: unknown;
  try {
    raw = JSON.parse(data);
  } catch {
    return null;
  }
  if (typeof raw !== "object" || raw === null) return null;
  const frame = raw as Record<string, unknown>;
  const id = typeof frame.id === "string" && frame.id !== "" ? frame.id : lastEventId;
  if (!id) return null;
  const parsed = StreamEventSchema.safeParse({ ...frame, id });
  return parsed.success ? parsed.data : null;
}

/**
 * An `EventSource` that the browser gave up on (`readyState === CLOSED`) means the server answered
 * with an HTTP error, typically `410 Gone` for an expired cursor: reconnect from a fresh snapshot.
 * While `CONNECTING` the browser is retrying on its own and the cursor is still good.
 */
export function shouldResetCursor(readyState: number): boolean {
  return readyState === 2;
}
