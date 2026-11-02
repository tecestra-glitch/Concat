"use client";
/** User settings persisted in localStorage via a tiny external store (hydration-safe). */
import * as React from "react";
import { type Mode, resolveMode } from "./api/client";

export interface Settings {
  modePreference: Mode | "auto";
  defaultCapital: number;
  valuationCurrency: "BRL" | "USD" | "PYG";
  pollFallbackSeconds: number;
}

export const DEFAULT_SETTINGS: Settings = { modePreference: "auto", defaultCapital: 5000, valuationCurrency: "BRL", pollFallbackSeconds: 30 };
const KEY = "fronteira-fx.settings.v1";

let current: Settings | null = null;
const listeners = new Set<() => void>();

function load(): Settings {
  if (current) return current;
  try {
    const raw = localStorage.getItem(KEY);
    current = raw ? { ...DEFAULT_SETTINGS, ...(JSON.parse(raw) as Partial<Settings>) } : DEFAULT_SETTINGS;
  } catch {
    current = DEFAULT_SETTINGS;
  }
  return current;
}

function subscribe(cb: () => void) {
  listeners.add(cb);
  return () => listeners.delete(cb);
}

export function updateSettings(patch: Partial<Settings>) {
  current = { ...load(), ...patch };
  try {
    localStorage.setItem(KEY, JSON.stringify(current));
  } catch {
    /* storage unavailable */
  }
  listeners.forEach((l) => l());
}

interface Ctx {
  settings: Settings;
  mode: Mode;
  update: (patch: Partial<Settings>) => void;
}

const SettingsContext = React.createContext<Ctx | null>(null);

export function SettingsProvider({ children }: { children: React.ReactNode }) {
  const settings = React.useSyncExternalStore(subscribe, load, () => DEFAULT_SETTINGS);
  const mode = resolveMode(settings.modePreference);
  const value = React.useMemo(() => ({ settings, mode, update: updateSettings }), [settings, mode]);
  return <SettingsContext.Provider value={value}>{children}</SettingsContext.Provider>;
}

export function useSettings(): Ctx {
  const ctx = React.useContext(SettingsContext);
  if (!ctx) throw new Error("useSettings fora de SettingsProvider");
  return ctx;
}
