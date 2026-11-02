/**
 * Toasts for `alert.fired` stream events, as a tiny external store (no `setState` in effects:
 * the SSE handler pushes here and the UI subscribes with `useSyncExternalStore`).
 */
import { useSyncExternalStore } from "react";
import type { AlertEvent } from "./api/watch";

const MAX = 20;
const EMPTY: AlertEvent[] = [];

let toasts: AlertEvent[] = EMPTY;
const listeners = new Set<() => void>();

function emit() {
  for (const l of listeners) l();
}

export const alertToasts = {
  /** Current list, newest first; the reference is stable until the list changes. */
  get(): AlertEvent[] {
    return toasts;
  },
  subscribe(cb: () => void): () => void {
    listeners.add(cb);
    return () => {
      listeners.delete(cb);
    };
  },
  /** Add an event (ignored when an event with the same id is already shown). */
  push(ev: AlertEvent): void {
    if (toasts.some((t) => t.id === ev.id)) return;
    toasts = [ev, ...toasts].slice(0, MAX);
    emit();
  },
  dismiss(id: string): void {
    if (!toasts.some((t) => t.id === id)) return;
    toasts = toasts.filter((t) => t.id !== id);
    emit();
  },
  clear(): void {
    if (toasts.length === 0) return;
    toasts = EMPTY;
    emit();
  },
};

/** Subscribe a component to the toast list (empty on the server). */
export function useAlertToasts(): AlertEvent[] {
  return useSyncExternalStore(alertToasts.subscribe, alertToasts.get, () => EMPTY);
}
