"use client";
/**
 * Cotações e fontes da tela de pregão no modo resolvido (§24.4). `useQuotes()` e `useSources()` rodam
 * nos dois modos (regra dos hooks); em demo as cotações usadas são as de `demoQuotesAt(now)`, com
 * idades relativas ao relógio da tela (§0.9), e as fontes são as que o cliente de API já devolve.
 */
import { useMemo } from "react";
import type { Mode } from "@/lib/api/client";
import type { Quote, Source } from "@/lib/api/types";
import { useQuotes, useSources } from "@/lib/queries";
import { useSettings } from "@/lib/settings";
import { demoQuotesAt } from "./demo";

const NO_QUOTES: Quote[] = [];
const NO_SOURCES: Source[] = [];

/** Puro: em demo, as cotações recarimbadas (vazio enquanto `now === 0`); senão as da API. */
export function pregaoQuotesFor(mode: Mode, fetched: Quote[], now: number): Quote[] {
  if (mode !== "demo") return fetched;
  return now === 0 ? NO_QUOTES : demoQuotesAt(new Date(now));
}

/** Puro: em demo os dados são locais, então a consulta de rede não manda em carregando nem em erro. */
export function pregaoQuotesStatus(mode: Mode, q: { isPending: boolean; error: Error | null; hasData: boolean }): { isPending: boolean; error: Error | null } {
  if (mode === "demo") return { isPending: false, error: null };
  return { isPending: q.isPending, error: q.hasData ? null : q.error };
}

export interface PregaoQuotes {
  quotes: Quote[];
  sources: Source[];
  isPending: boolean;
  /** Erro só quando ainda não há dados (refetch que falha mantém as cotações já mostradas). */
  error: Error | null;
  refetch: () => void;
}

export function usePregaoQuotes(now: number): PregaoQuotes {
  const { mode } = useSettings();
  const quotesQ = useQuotes();
  const sourcesQ = useSources();
  const fetched = quotesQ.data ?? NO_QUOTES;
  const quotes = useMemo(() => pregaoQuotesFor(mode, fetched, now), [mode, fetched, now]);
  const status = pregaoQuotesStatus(mode, { isPending: quotesQ.isPending, error: quotesQ.error, hasData: quotesQ.data !== undefined });
  return {
    quotes,
    sources: sourcesQ.data ?? NO_SOURCES,
    ...status,
    refetch: () => void quotesQ.refetch(),
  };
}
