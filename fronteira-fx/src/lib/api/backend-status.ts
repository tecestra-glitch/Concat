/**
 * Backend availability as a tiny external store (hydration-safe, `useSyncExternalStore`).
 *
 * The browser never knows the backend URL (D5: everything goes through `/api/fx`), so "is there a
 * backend?" is answered by probing `/v1/health` once through the proxy. `modePreference = "auto"`
 * resolves to `real` only after the probe succeeds; until then (and on the server) it is `demo`.
 */
import type { BackendHealth } from "./types";
import { http } from "./client";

export type BackendStatus = "unknown" | "available" | "unavailable";

const REPROBE_MS = 60_000;

let status: BackendStatus = "unknown";
let probing: Promise<void> | null = null;
let reprobe: ReturnType<typeof setInterval> | null = null;
const listeners = new Set<() => void>();

export function getBackendStatus(): BackendStatus {
  return status;
}

/** Server snapshot: the server never probes, so SSR and the first client render agree on "unknown". */
export function getServerBackendStatus(): BackendStatus {
  return "unknown";
}

export function setBackendStatus(next: BackendStatus): void {
  if (next === status) return;
  status = next;
  for (const l of listeners) l();
}

/** One probe at a time; a failed proxy call (503 without FX_API_URL, network error) means unavailable. */
export function probeBackend(): Promise<void> {
  if (probing) return probing;
  probing = http<BackendHealth>("/v1/health")
    .then((h) => setBackendStatus(h && typeof h.status === "string" ? "available" : "unavailable"))
    .catch(() => setBackendStatus("unavailable"))
    .finally(() => {
      probing = null;
    });
  return probing;
}

export function subscribeBackendStatus(cb: () => void): () => void {
  listeners.add(cb);
  if (typeof window !== "undefined") {
    if (status === "unknown") void probeBackend();
    // While someone is listening, re-probe slowly so a backend that comes up later is noticed.
    if (!reprobe) reprobe = setInterval(() => void probeBackend(), REPROBE_MS);
  }
  return () => {
    listeners.delete(cb);
    if (listeners.size === 0 && reprobe) {
      clearInterval(reprobe);
      reprobe = null;
    }
  };
}
