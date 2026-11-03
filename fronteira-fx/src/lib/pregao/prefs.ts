"use client";
/**
 * Preferências da tela de pregão (D32, D47): o intervalo, os indicadores e a fita pausada, em `localStorage`
 * (chave `fx.pregao.prefs`). Store externo com `useSyncExternalStore`, mesmo padrão de
 * `src/lib/settings.tsx`: o servidor e a hidratação veem `DEFAULT_PREFS`; a gravação acontece só
 * nos handlers (`updatePregaoPrefs`), nunca num efeito.
 */
import { useSyncExternalStore } from "react";
import { INDICATOR_DEFAULTS, TIMEFRAMES, type IndicatorState, type Timeframe } from "./types";

export interface PregaoPrefs {
  tf: Timeframe;
  indicators: IndicatorState;
  /** Fita de cotações parada pelo botão "Pausar fita" (WCAG 2.2.2: no toque não há hover nem foco para pausar). */
  tapePaused: boolean;
}

export const DEFAULT_PREFS: PregaoPrefs = { tf: "1h", indicators: INDICATOR_DEFAULTS, tapePaused: false };
export const PREFS_KEY = "fx.pregao.prefs";

const INDICATOR_IDS = Object.keys(INDICATOR_DEFAULTS) as (keyof IndicatorState)[];

const isRecord = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);

/** Valida o JSON gravado campo a campo: o que não for válido volta ao padrão. */
export function parsePrefs(raw: string | null): PregaoPrefs {
  if (raw === null) return DEFAULT_PREFS;
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return DEFAULT_PREFS;
  }
  if (!isRecord(parsed)) return DEFAULT_PREFS;
  const tf = TIMEFRAMES.find((t) => t === parsed.tf) ?? DEFAULT_PREFS.tf;
  const stored = isRecord(parsed.indicators) ? parsed.indicators : {};
  const indicators = { ...INDICATOR_DEFAULTS };
  for (const id of INDICATOR_IDS) {
    const v = stored[id];
    if (typeof v === "boolean") indicators[id] = v;
  }
  const tapePaused = typeof parsed.tapePaused === "boolean" ? parsed.tapePaused : DEFAULT_PREFS.tapePaused;
  return { tf, indicators, tapePaused };
}

let current: PregaoPrefs | null = null;
const listeners = new Set<() => void>();

/** Preferências atuais (lidas do `localStorage` uma vez; padrão quando ele não existe ou falha). */
export function readPregaoPrefs(): PregaoPrefs {
  if (current) return current;
  try {
    current = parsePrefs(localStorage.getItem(PREFS_KEY));
  } catch {
    current = DEFAULT_PREFS;
  }
  return current;
}

export function subscribePregaoPrefs(cb: () => void): () => void {
  listeners.add(cb);
  return () => {
    listeners.delete(cb);
  };
}

export function usePregaoPrefs(): PregaoPrefs {
  return useSyncExternalStore(subscribePregaoPrefs, readPregaoPrefs, () => DEFAULT_PREFS);
}

/** Mescla, grava (sem lançar quando o storage falha) e avisa os inscritos. Chamar só em handlers. */
export function updatePregaoPrefs(patch: Partial<PregaoPrefs>): void {
  current = { ...readPregaoPrefs(), ...patch };
  try {
    localStorage.setItem(PREFS_KEY, JSON.stringify(current));
  } catch {
    /* storage indisponível: a preferência vale só nesta aba */
  }
  listeners.forEach((l) => l());
}

export function resetPregaoPrefsForTests(): void {
  current = null;
  listeners.clear();
}
