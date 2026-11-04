/**
 * Realce de célula que mudou. Não é elemento Uiverse: é lógica do app (regra: um realce curto por mudança de valor,
 * nunca por re-render, e nada se move sobre o número).
 *
 * `useFlash(value)` devolve `fx-flash-up` ou `fx-flash-down` no render em que o valor muda de sentido (número para
 * número); em qualquer outro caso, `undefined`. Como a animação só roda quando a classe entra, repetições no mesmo
 * sentido alternam o sufixo `-b` (mesmos keyframes, outro nome), para que cada mudança realmente pisque.
 * Usa só ajuste de estado durante o render (sem `setState` em `useEffect`, regra do projeto).
 */
import { useState } from "react";

export type FlashClass = "fx-flash-up" | "fx-flash-down" | "fx-flash-up-b" | "fx-flash-down-b";
export type FlashValue = string | number | null | undefined;

export interface FlashState {
  value: FlashValue;
  cls: FlashClass | undefined;
  alt: boolean;
}

export function toFlashNumber(v: unknown): number | null {
  if (typeof v === "number") return Number.isFinite(v) ? v : null;
  if (typeof v === "string" && v.trim() !== "") {
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  }
  return null;
}

/**
 * Próximo estado do realce. Igual ao anterior → sem realce (a classe anterior sai só na mudança seguinte).
 * Sem número nos dois lados (primeira carga, nulo) → sem realce. Mudança numérica → sentido e sufixo alternado.
 */
export function flashStep(state: FlashState, value: FlashValue): FlashState {
  if (state.value === value) return state;
  const from = toFlashNumber(state.value);
  const to = toFlashNumber(value);
  if (from === null || to === null || from === to) {
    return { value, cls: undefined, alt: state.alt };
  }
  const alt = !state.alt;
  const dir = to > from ? "up" : "down";
  return { value, cls: `fx-flash-${dir}${alt ? "-b" : ""}` as FlashClass, alt };
}

export function useFlash(value: FlashValue): FlashClass | undefined {
  const [state, setState] = useState<FlashState>({ value, cls: undefined, alt: false });
  if (state.value !== value) {
    setState(flashStep(state, value));
  }
  return state.cls;
}
