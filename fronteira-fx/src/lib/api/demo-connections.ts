/**
 * Modo demo das conexões: dados fictícios, marcados como demonstração, sem rede. A validação de chave aqui é uma
 * heurística de teste (a chave de demonstração que contiver "trade" ou "withdraw" é tratada como perigosa), para
 * a recusa poder ser vista; a validação real acontece no servidor.
 */
import { keyTail, type ApiKeyValidation, type Connection, type ConnectionList, type StatementImportResult } from "./connections";

const DEMO_TIME = "2026-11-04T09:00:00.000Z";

const seed = (): Connection[] => [
  {
    id: "demo-conn-1",
    institution_id: "binance",
    institution_name: "Binance",
    method: "api_key_readonly",
    status: "active",
    key_hint: "9f2K",
    created_at: DEMO_TIME,
    last_sync_at: DEMO_TIME,
    data_mode: "demo",
  },
];

let store: Connection[] | null = null;
let counter = 0;

function list(): Connection[] {
  if (!store) store = seed();
  return store;
}

/** Lista de demonstração. Agregador marcado como não configurado, para mostrar o aviso de contratação. */
export function demoConnectionList(): ConnectionList {
  return { aggregator_configured: false, connections: list().map((c) => ({ ...c })) };
}

/** Heurística de demonstração: chave com "trade" ou "withdraw" no texto é recusada. */
export function demoValidateApiKey(apiKey: string): ApiKeyValidation {
  const lower = apiKey.toLowerCase();
  return { read: true, trade: lower.includes("trade"), withdraw: lower.includes("withdraw") };
}

/** Cria a conexão de demonstração. Guarda só a dica da chave; o segredo nunca entra aqui. */
export function demoCreateApiKeyConnection(input: { institution_id: string; institution_name: string; api_key: string }): Connection {
  const conn: Connection = {
    id: `demo-local-${++counter}`,
    institution_id: input.institution_id,
    institution_name: input.institution_name,
    method: "api_key_readonly",
    status: "active",
    key_hint: keyTail(input.api_key),
    created_at: DEMO_TIME,
    last_sync_at: null,
    data_mode: "demo",
  };
  list().push(conn);
  return conn;
}

/** Importação de demonstração: o arquivo não sai do navegador e nenhuma linha é lida. */
export function demoImportStatement(input: { institution_id: string; institution_name: string }): StatementImportResult {
  const conn: Connection = {
    id: `demo-local-${++counter}`,
    institution_id: input.institution_id,
    institution_name: input.institution_name,
    method: "statement_import",
    status: "pending",
    key_hint: null,
    created_at: DEMO_TIME,
    last_sync_at: null,
    data_mode: "demo",
  };
  list().push(conn);
  return { connection: conn, rows_read: 0, rows_skipped: 0 };
}

export function demoDeleteConnection(id: string): void {
  store = list().filter((c) => c.id !== id);
}

export function resetDemoConnections(): void {
  store = null;
}
