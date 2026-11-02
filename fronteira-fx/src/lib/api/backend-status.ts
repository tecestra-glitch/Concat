/**
 * Backend availability as a tiny external store (hydration-safe, `useSyncExternalStore`).
 *
 * The browser never knows the backend URL (D5: everything goes through `/api/fx`), so "is there a
 * backend?" is answered by probing `/v1/health` once through the proxy. `modePreference = "auto"`
 * resolves to the mode the instance declares only after the probe succeeds; until then (and on the
 * server) it is `demo`. The declared mode is kept next to the status (SEC-01: each instance serves one mode).
 */
import type { BackendHealth, Mode } from "./types";
import { http } from "./client";

export type BackendStatus = "unknown" | "available" | "unavailable";

const REPROBE_MS = 60_000;

let status: BackendStatus = "unknown";
let backendMode: Mode | null = null;
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

/** The `data_mode` the instance declared in its last health answer (`null` until then or when it is down). */
export function getBackendMode(): Mode | null {
  return backendMode;
}

export function getServerBackendMode(): Mode | null {
  return null;
}

const MODES: readonly Mode[] = ["real", "simulation", "demo"];

export function setBackendStatus(next: BackendStatus, mode?: string | null): void {
  const nextMode = next === "available" && MODES.includes(mode as Mode) ? (mode as Mode) : next === "available" ? backendMode : null;
  if (next === status && nextMode === backendMode) return;
  status = next;
  backendMode = nextMode;
  for (const l of listeners) l();
}

/** One probe at a time; a failed proxy call (503 without FX_API_URL, network error) means unavailable. */
export function probeBackend(): Promise<void> {
  if (probing) return probing;
  probing = http<BackendHealth>("/v1/health")
    .then((h) => (h && typeof h.status === "string" ? setBackendStatus("available", h.data_mode) : setBackendStatus("unavailable")))
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
