/**
 * Volatility per comparable context: 5-minute grid, sample stdev of log returns,
 * unit "% por intervalo de 5 min", min 6 valid returns. A re-captured quote whose
 * declared timestamp did not change is NOT a new observation.
 */
export interface Obs {
  t: number; // epoch ms (captured_at)
  value: number; // mid or chosen side
  declared?: string | null; // declared_updated_at, used to drop re-captures
}

export interface VolResult {
  stdevPctPer5m: number | null;
  returnsUsed: number;
  minReturns: number;
  coveragePct: number;
  gaps: number;
  status: "ok" | "insufficient_data" | "stale_input";
}

export const GRID_MS = 5 * 60 * 1000;
export const MIN_RETURNS = 6;

export function dedupeStale(obs: Obs[]): Obs[] {
  const out: Obs[] = [];
  let lastDeclared: string | null | undefined = undefined;
  for (const o of [...obs].sort((a, b) => a.t - b.t)) {
    if (o.declared && o.declared === lastDeclared) continue; // same declared quote re-captured
    out.push(o);
    lastDeclared = o.declared;
  }
  return out;
}

/** Snap observations to a 5-minute grid (last value wins within a bucket). */
export function toGrid(obs: Obs[], windowMs: number, now: number): (number | null)[] {
  const start = Math.floor((now - windowMs) / GRID_MS) * GRID_MS;
  const slots = Math.round(windowMs / GRID_MS) + 1; // inclusive of the latest bucket
  const grid: (number | null)[] = new Array(slots).fill(null);
  for (const o of obs) {
    const i = Math.floor((o.t - start) / GRID_MS);
    if (i >= 0 && i < slots) grid[i] = o.value;
  }
  return grid;
}

export function computeVolatility(raw: Obs[], windowMs: number, now: number = Date.now()): VolResult {
  const obs = dedupeStale(raw).filter((o) => o.value > 0 && o.t <= now && o.t >= now - windowMs);
  const grid = toGrid(obs, windowMs, now);
  const filled = grid.filter((v) => v !== null).length;
  const coveragePct = grid.length ? (filled / grid.length) * 100 : 0;
  let gaps = 0;
  for (let i = 1; i < grid.length; i++) if (grid[i] === null && grid[i - 1] !== null) gaps++;

  const returns: number[] = [];
  for (let i = 1; i < grid.length; i++) {
    const a = grid[i - 1];
    const b = grid[i];
    if (a !== null && b !== null) returns.push(Math.log(b / a));
  }
  if (raw.length > 0 && obs.length <= 1 && raw.length > obs.length) {
    return { stdevPctPer5m: null, returnsUsed: returns.length, minReturns: MIN_RETURNS, coveragePct, gaps, status: "stale_input" };
  }
  if (returns.length < MIN_RETURNS) {
    return { stdevPctPer5m: null, returnsUsed: returns.length, minReturns: MIN_RETURNS, coveragePct, gaps, status: "insufficient_data" };
  }
  const mean = returns.reduce((s, r) => s + r, 0) / returns.length;
  const varS = returns.reduce((s, r) => s + (r - mean) ** 2, 0) / (returns.length - 1);
  return { stdevPctPer5m: Math.sqrt(varS) * 100, returnsUsed: returns.length, minReturns: MIN_RETURNS, coveragePct, gaps, status: "ok" };
}
