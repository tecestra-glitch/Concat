"use client";
import { useSyncExternalStore } from "react";

/**
 * Relógios compartilhados por todos os assinantes. `useNow` bate a cada 30 s (telas gerais); `useSecondNow` bate
 * a cada 1 s (contagens regressivas, como a cotação de um plano, que não podem ficar congeladas). Devolvem 0 no servidor.
 */
function makeClock(periodMs: number) {
  let now = 0;
  const listeners = new Set<() => void>();
  let timer: ReturnType<typeof setInterval> | null = null;

  function subscribe(cb: () => void) {
    listeners.add(cb);
    if (!timer) {
      now = Date.now();
      timer = setInterval(() => {
        now = Date.now();
        listeners.forEach((l) => l());
      }, periodMs);
    }
    return () => {
      listeners.delete(cb);
      if (listeners.size === 0 && timer) {
        clearInterval(timer);
        timer = null;
      }
    };
  }

  const snapshot = () => (now === 0 ? (now = Date.now()) : now);
  return { subscribe, snapshot };
}

const slowClock = makeClock(30_000);
const secondClock = makeClock(1_000);

export function useNow(): number {
  return useSyncExternalStore(slowClock.subscribe, slowClock.snapshot, () => 0);
}

/** Relógio de 1 s: use em telas com contagem regressiva (prazo de um plano). */
export function useSecondNow(): number {
  return useSyncExternalStore(secondClock.subscribe, secondClock.snapshot, () => 0);
}

/** true after hydration, false on the server and first client render. */
export function useMounted(): boolean {
  return useSyncExternalStore(() => () => {}, () => true, () => false);
}
