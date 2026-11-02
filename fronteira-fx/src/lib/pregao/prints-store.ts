import type { QueryClient } from "@tanstack/react-query";
import { historyKey } from "@/lib/api/demo-data";
import type { Quote, Source } from "@/lib/api/types";
import { houseName, quoteToPrint } from "./derive";
import type { Print } from "./types";

/** Módulo sem React: store externo das atualizações, lido por `useSyncExternalStore` em `use-prints.ts`. */
export const PRINTS_MAX = 200;

let prints: readonly Print[] = [];
const listeners = new Set<() => void>();

function emit(): void {
  listeners.forEach((l) => l());
}

export function subscribe(cb: () => void): () => void {
  listeners.add(cb);
  return () => {
    listeners.delete(cb);
  };
}

/** Mesma referência enquanto nada mudar. */
export function getSnapshot(): readonly Print[] {
  return prints;
}

/** Ignora id repetido; insere após os de `captured_at` maior ou igual (estável); corta em `PRINTS_MAX`. */
export function pushPrint(p: Print): void {
  if (prints.some((x) => x.id === p.id)) return;
  const t = Date.parse(p.captured_at);
  let at = prints.findIndex((x) => Date.parse(x.captured_at) < t);
  if (at === -1) at = prints.length;
  prints = [...prints.slice(0, at), p, ...prints.slice(at)].slice(0, PRINTS_MAX);
  emit();
}

/** Compara cada cotação com a última vista da mesma chave e devolve os prints novos. Cópia do mapa, nunca mutação. */
export function diffQuotes(
  seen: ReadonlyMap<string, Quote>,
  next: readonly Quote[],
  sources: readonly Source[],
): { prints: Print[]; seen: Map<string, Quote> } {
  const out = new Map(seen);
  const added: Print[] = [];
  for (const q of next) {
    const key = historyKey(q);
    const prev = seen.get(key);
    if (!prev || prev.id !== q.id || prev.captured_at !== q.captured_at) {
      const p = quoteToPrint(q, prev ?? null, houseName(sources as Source[], q.source_id));
      if (p !== null) added.push(p);
    }
    out.set(key, q);
  }
  return { prints: added, seen: out };
}

/** Assina o cache de queries; cada atualização de `["quotes", …]` vira prints. Devolve o unsubscribe. */
export function startPrintsFeed(qc: QueryClient): () => void {
  let seen = new Map<string, Quote>();
  return qc.getQueryCache().subscribe((ev) => {
    if (ev.type !== "added" && ev.type !== "updated") return;
    const k = ev.query.queryKey;
    if (k[0] !== "quotes") return;
    const data = ev.query.state.data;
    if (!Array.isArray(data)) return;
    const sources = qc.getQueryData<Source[]>(["sources", k[1]]) ?? [];
    const r = diffQuotes(seen, data as Quote[], sources);
    seen = r.seen;
    r.prints.forEach(pushPrint);
  });
}

export function resetPrintsForTests(): void {
  prints = [];
  emit();
}
