"use client";
import { useSyncExternalStore } from "react";

/** A clock that ticks every 30 s, shared by all subscribers. Returns 0 on the server. */
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
    }, 30_000);
  }
  return () => {
    listeners.delete(cb);
    if (listeners.size === 0 && timer) {
      clearInterval(timer);
      timer = null;
    }
  };
}

export function useNow(): number {
  return useSyncExternalStore(subscribe, () => (now === 0 ? (now = Date.now()) : now), () => 0);
}

/** true after hydration, false on the server and first client render. */
export function useMounted(): boolean {
  return useSyncExternalStore(() => () => {}, () => true, () => false);
}
