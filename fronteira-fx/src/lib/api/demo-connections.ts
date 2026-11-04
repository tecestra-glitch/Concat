/**
 * Modo demo das conexões: dados fictícios, marcados como demonstração, sem rede. A validação de chave aqui é uma
 * heurística de teste (chave de demonstração que contiver "trade" ou "withdraw" é tratada como perigosa), para a
 * recusa poder ser vista; a validação real acontece no servidor.
 */
import { TRADE_FLAGS, WITHDRAW_FLAGS, keyTail, type ApiKeyValidation, type Connection, type ConnectionList, type StatementImportResult } from "./connections";

const DEMO_TIME = "2026-11-04T09:00:00.000Z";

const seed = (): Connection[] => [
  {
    id: "demo-conn-1",
    institution: "binance",
    label: "Binance leitura",
    kind: "readonly_key",
    status: "active",
    data_mode: "demo",
    account_id: null,
    key_hint: "9f2K",
    balances: [{ asset: "USDT", free: "120.5", locked: "0" }],
    last_error: null,
    last_synced_at: DEMO_TIME,
    created_at: DEMO_TIME,
    updated_at: DEMO_TIME,
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

/** Heurística de demonstração: chave com "trade" ou "withdraw" no texto é recusada. Formato igual ao KeyCheckOut. */
export function demoValidateApiKey(apiKey: string): ApiKeyValidation {
  const lower = apiKey.toLowerCase();
  const trade = lower.includes("trade");
  const withdraw = lower.includes("withdraw");
  return {
    ok: !trade && !withdraw,
    institution: "demo",
    flags: {
      enableReading: true,
      ...Object.fromEntries(TRADE_FLAGS.map((f) => [f, trade])),
      ...Object.fromEntries(WITHDRAW_FLAGS.map((f) => [f, withdraw])),
    },
    reasons: [],
    balances: [],
  };
}

/** Cria a conexão de demonstração. Guarda só a dica da chave; o segredo nunca entra aqui. */
export function demoCreateApiKeyConnection(input: { institution: string; label: string; api_key: string }): Connection {
  const conn: Connection = {
    id: `demo-local-${++counter}`,
    institution: input.institution,
    label: input.label,
    kind: "readonly_key",
    status: "active",
    data_mode: "demo",
    account_id: null,
    key_hint: keyTail(input.api_key),
    balances: [],
    last_error: null,
    last_synced_at: null,
    created_at: DEMO_TIME,
    updated_at: DEMO_TIME,
  };
  list().push(conn);
  return conn;
}

/** Conexão de extrato de demonstração (ainda sem linhas). */
export function demoCreateStatementConnection(input: { institution: string; label: string }): Connection {
  const conn: Connection = {
    id: `demo-local-${++counter}`,
    institution: input.institution,
    label: input.label,
    kind: "statement",
    status: "pending",
    data_mode: "demo",
    account_id: null,
    key_hint: null,
    balances: null,
    last_error: null,
    last_synced_at: null,
    created_at: DEMO_TIME,
    updated_at: DEMO_TIME,
  };
  list().push(conn);
  return conn;
}

/** Importação de demonstração: o arquivo não sai do navegador e nenhuma linha é lida. */
export function demoImportStatement(connection: Connection, format: "csv" | "ofx"): StatementImportResult {
  return { connection_id: connection.id, format, imported: 0, duplicates: 0, account_id: null, balance_delta: "0", account_balance_free: null };
}

export function demoDeleteConnection(id: string): void {
  store = list().filter((c) => c.id !== id);
}

export function resetDemoConnections(): void {
  store = null;
}
