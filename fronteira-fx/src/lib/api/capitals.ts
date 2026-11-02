/**
 * Capital presets for the opportunity filters. `DEMO_CAPITALS` is demo-only (plan F8): in real and
 * simulation modes the list is the standard amounts plus the user's default capital.
 */
import { DEMO_CAPITALS } from "./demo-data";
import type { Mode } from "./types";

export const STANDARD_CAPITALS: readonly number[] = [5000, 10000, 25000, 50000];

export function capitalOptions(mode: Mode, defaultCapital: number): number[] {
  if (mode === "demo") return [...DEMO_CAPITALS];
  const set = new Set<number>(STANDARD_CAPITALS);
  if (Number.isFinite(defaultCapital) && defaultCapital > 0) set.add(defaultCapital);
  return [...set].sort((a, b) => a - b);
}
