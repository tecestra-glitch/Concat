"use client";
import { useSyncExternalStore } from "react";

/**
 * A 1-second clock shared by every countdown on the page (same pattern as src/lib/use-now.ts,
 * which ticks every 30 s). Returns 0 on the server and on the first client render.
 */
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
    }, 1000);
  }
  return () => {
    listeners.delete(cb);
    if (listeners.size === 0 && timer) {
      clearInterval(timer);
      timer = null;
    }
  };
}

export function useTicker(): number {
  return useSyncExternalStore(subscribe, () => (now === 0 ? (now = Date.now()) : now), () => 0);
}
