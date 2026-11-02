/**
 * Telas mínimas de RAG e memória (contrato: módulos `rag` e `memory`). O cliente de src/lib/api
 * não expõe estes dois GETs; aqui só montamos o caminho e usamos o `http()` único do projeto.
 * Em demonstração nada toca a rede: as listas são vazias e a tela explica o porquê.
 */
import { http, modeQuery, qs, type Mode } from "@/lib/api/client";
import type { Memory } from "@/lib/api/types";

export interface KnowledgeHit {
  id: string;
  document_id: string;
  title: string;
  snippet: string;
  score: number | string;
  source: string;
  tags: string[];
}

export interface KnowledgeQuery {
  q: string;
  k: number;
  tag: string;
}

export interface MemoryItem extends Memory {
  expires_at?: string | null;
  source?: string;
}

export interface MemoryQuery {
  q: string;
  kind: string;
  tag: string;
  limit: number;
}

export function knowledgeSearchPath(mode: Mode, f: KnowledgeQuery): string {
  return `/v1/rag/search${qs({ q: f.q, k: f.k, tag: f.tag, ...modeQuery(mode) })}`;
}

export function memoryListPath(mode: Mode, f: MemoryQuery): string {
  return `/v1/memory${qs({ q: f.q, kind: f.kind, tag: f.tag, limit: f.limit, ...modeQuery(mode) })}`;
}

export async function searchKnowledge(mode: Mode, f: KnowledgeQuery): Promise<KnowledgeHit[]> {
  if (mode === "demo") return [];
  return http<KnowledgeHit[]>(knowledgeSearchPath(mode, f));
}

export async function listMemory(mode: Mode, f: MemoryQuery): Promise<MemoryItem[]> {
  if (mode === "demo") return [];
  return http<MemoryItem[]>(memoryListPath(mode, f));
}
