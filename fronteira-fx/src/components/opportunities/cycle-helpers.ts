import type { Currency, Cycle } from "@/lib/api/types";
import { toNumber } from "@/lib/format";

/** Moeda do nó inicial (`BRL@brbank` → BRL). */
export function cycleCurrency(node: string): Currency {
  return node.split("@")[0] as Currency;
}

/** D1: `gain` é string decimal; comparar como número (em string, "9" > "10"). */
export function isProfitable(c: Cycle): boolean {
  return (toNumber(c.gain) ?? 0) > 0;
}

export function formatMinutes(minutes: number): string {
  return minutes >= 1440 ? `${(minutes / 1440).toFixed(1).replace(".", ",")} d` : `${minutes} min`;
}
