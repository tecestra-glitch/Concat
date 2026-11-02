"use client";
import { useEffect, useRef } from "react";
import type { Timeframe } from "./types";

export interface HotkeyBinding {
  /** KeyboardEvent.key: "1".."4", "[", "]", "?", "Escape". */
  key: string;
  group: "Gráfico" | "Par" | "Ajuda";
  /** Texto exato de §0.14, mostrado no diálogo de atalhos. */
  description: string;
  handler: () => void;
  /** Padrão false. Quando true, o atalho também funciona com o foco dentro de um diálogo. */
  allowInDialog?: boolean;
}

export type HotkeyEventLike = Pick<KeyboardEvent, "key" | "ctrlKey" | "metaKey" | "altKey" | "target">;

/**
 * Forma mínima de um alvo de evento. No navegador é um `Element`; em Node (testes, sem DOM)
 * aceitamos qualquer objeto com `tagName: string` e `closest()` (duck typing).
 */
interface ElementLike {
  tagName: string;
  isContentEditable?: boolean;
  closest: (selector: string) => unknown;
}

function asElementLike(target: EventTarget | null): ElementLike | null {
  if (typeof Element !== "undefined" && target instanceof Element) return target as unknown as ElementLike;
  if (target && typeof target === "object") {
    const t = target as Partial<ElementLike>;
    if (typeof t.tagName === "string" && typeof t.closest === "function") return t as ElementLike;
  }
  return null;
}

/** Campo de texto: input, textarea, select ou conteúdo editável. Atalhos não disparam nesses casos. */
export function isTextTarget(target: EventTarget | null): boolean {
  const el = asElementLike(target);
  if (!el) return false;
  const tag = el.tagName.toUpperCase();
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return true;
  if (el.isContentEditable) return true;
  return Boolean(el.closest("[contenteditable='true']"));
}

/** Alvo dentro de um diálogo (`[role="dialog"]`). */
export function inDialog(target: EventTarget | null): boolean {
  const el = asElementLike(target);
  return el !== null && Boolean(el.closest('[role="dialog"]'));
}

/** Casa o evento com um binding, ou devolve null. Puro: testável sem DOM. */
export function matchHotkey(ev: HotkeyEventLike, bindings: readonly HotkeyBinding[]): HotkeyBinding | null {
  if (ev.ctrlKey || ev.metaKey || ev.altKey) return null;
  if (isTextTarget(ev.target)) return null;
  const binding = bindings.find((b) => b.key === ev.key);
  if (!binding) return null;
  if (inDialog(ev.target) && !binding.allowInDialog) return null;
  return binding;
}

/**
 * Registra os atalhos na janela. A lista fica numa ref atualizada por efeito sem dependências,
 * então o listener não é recriado a cada render e os handlers sempre veem o estado atual.
 */
export function useHotkeys(bindings: readonly HotkeyBinding[], enabled = true): void {
  const ref = useRef(bindings);
  useEffect(() => {
    ref.current = bindings;
  });
  useEffect(() => {
    if (!enabled) return;
    const onKey = (e: KeyboardEvent) => {
      const binding = matchHotkey(e, ref.current);
      if (binding) {
        e.preventDefault();
        binding.handler();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [enabled]);
}

function timeframeBinding(a: BindingActions, key: string, tf: Timeframe, description: string): HotkeyBinding {
  return { key, group: "Gráfico", description, handler: () => a.setTimeframe(tf) };
}

interface BindingActions {
  setTimeframe: (tf: Timeframe) => void;
  cyclePair: (dir: 1 | -1) => void;
  toggleHelp: () => void;
  escape: () => void;
}

/** As oito entradas de §0.14, na ordem da tabela. */
export function buildPregaoBindings(a: BindingActions): HotkeyBinding[] {
  return [
    timeframeBinding(a, "1", "15m", "Velas de 15 minutos"),
    timeframeBinding(a, "2", "1h", "Velas de 1 hora"),
    timeframeBinding(a, "3", "4h", "Velas de 4 horas"),
    timeframeBinding(a, "4", "1d", "Velas de 1 dia"),
    { key: "[", group: "Par", description: "Par anterior", handler: () => a.cyclePair(-1) },
    { key: "]", group: "Par", description: "Próximo par", handler: () => a.cyclePair(1) },
    { key: "?", group: "Ajuda", description: "Mostrar esta ajuda", handler: () => a.toggleHelp(), allowInDialog: true },
    { key: "Escape", group: "Ajuda", description: "Fechar", handler: () => a.escape(), allowInDialog: true },
  ];
}
