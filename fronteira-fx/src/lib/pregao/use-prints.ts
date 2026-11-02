"use client";
import { useEffect, useMemo, useSyncExternalStore } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { Mode } from "@/lib/api/client";
import { useSettings } from "@/lib/settings";
import { useNow } from "@/lib/use-now";
import { demoPrints } from "./demo";
import { getSnapshot, startPrintsFeed, subscribe } from "./prints-store";
import type { Print } from "./types";

const EMPTY: readonly Print[] = [];

/** Atualizações reais, lidas do store que `usePrintsFeed` alimenta a partir do cache de cotações. */
export function usePrints(limit = 30): readonly Print[] {
  const all = useSyncExternalStore(subscribe, getSnapshot, () => EMPTY);
  return useMemo(() => all.slice(0, limit), [all, limit]);
}

/** Atualizações demo derivadas do relógio da tela (atualiza a cada 30 s). */
export function useDemoPrints(limit = 30): readonly Print[] {
  const now = useNow();
  return useMemo(() => (now ? demoPrints(new Date(now), limit) : EMPTY), [now, limit]);
}

/** Chama os dois hooks sempre, para a ordem dos hooks não mudar com o modo, e devolve o do modo atual. */
export function usePrintsFor(mode: Mode, limit = 30): readonly Print[] {
  const real = usePrints(limit);
  const demo = useDemoPrints(limit);
  return mode === "demo" ? demo : real;
}

/** Liga o store às cotações do cache em modo real. Chamar uma vez por página. */
export function usePrintsFeed(): void {
  const qc = useQueryClient();
  const { mode } = useSettings();
  useEffect(() => (mode === "real" ? startPrintsFeed(qc) : undefined), [qc, mode]);
}
