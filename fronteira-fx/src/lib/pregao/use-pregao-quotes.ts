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
  return {
    quotes,
    sources: sourcesQ.data ?? NO_SOURCES,
    isPending: quotesQ.isPending,
    error: quotesQ.data ? null : quotesQ.error,
    refetch: () => void quotesQ.refetch(),
  };
}
