import { countRecent, type Change } from "@/lib/api/watch";

export interface ChangeCounts {
  lastHour: number | null;
  last24h: number | null;
}

/** Contagens reais por janela; `now === 0` (antes da hidratação) devolve nulos para o placeholder. */
export function changeCounts(changes: Change[], now: number): ChangeCounts {
  if (now === 0) return { lastHour: null, last24h: null };
  return { lastHour: countRecent(changes, now, 3600), last24h: countRecent(changes, now, 86_400) };
}
