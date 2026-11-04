/**
 * Teste de contrato: o front de conexões tem de bater com o openapi exportado do backend
 * (`src/test/fixtures/connections-openapi.json`, subconjunto de `docs/openapi.json` em 3138bbd). Confere:
 * - os campos dos schemas de resposta (zod) são exatamente os do openapi;
 * - cada corpo que o cliente envia tem só campos do openapi e cobre os obrigatórios;
 * - cada rota chamada existe no openapi com o método certo.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import spec from "./fixtures/connections-openapi.json";
import { BalanceSchema, ApiKeyValidationSchema, ConnectionSchema, StatementImportResultSchema } from "@/lib/api/connections";
import { api } from "@/lib/api/client";

type Schema = { properties: Record<string, unknown>; required?: string[] };
const schemas = spec.schemas as unknown as Record<string, Schema>;
const paths = spec.paths as unknown as Record<string, Record<string, unknown>>;

const keys = (o: object) => Object.keys(o).sort();

let calls: { method: string; path: string; body: unknown }[] = [];
let fetchMock: ReturnType<typeof vi.fn>;

const CONN_ID = "c-9";
const connRow = { id: CONN_ID, institution: "binance", label: "Binance leitura", kind: "readonly_key", status: "active", data_mode: "real", account_id: null, key_hint: "9f2K", balances: [], last_error: null, last_synced_at: null, created_at: "2026-11-04T09:00:00Z", updated_at: "2026-11-04T09:00:00Z" };

const json = (body: unknown, status = 200) => new Response(body === undefined ? null : JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

beforeEach(() => {
  calls = [];
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const u = new URL(url, "http://localhost");
    const path = u.pathname.replace(/^\/api\/fx/, "");
    const method = (init?.method ?? "GET").toUpperCase();
    calls.push({ method, path, body: typeof init?.body === "string" ? JSON.parse(init.body) : undefined });
    if (method === "GET") return json([connRow]);
    if (method === "DELETE") return new Response(null, { status: 204 });
    if (path.endsWith("/validate-key")) return json({ ok: true, institution: "binance", flags: { enableWithdrawals: false }, reasons: [], balances: [] });
    if (path.endsWith("/statement")) return json({ connection_id: CONN_ID, format: "csv", imported: 2, duplicates: 0, account_id: null, balance_delta: "0", account_balance_free: null });
    if (path.endsWith("/openfinance/consent")) return json({ detail: "Open Finance não configurado" }, 503);
    return json(connRow, 201);
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

/** Confere um corpo enviado contra um schema do openapi: só campos conhecidos e todos os obrigatórios presentes. */
function expectBodyMatches(body: unknown, schemaName: string) {
  const s = schemas[schemaName];
  const sent = body as Record<string, unknown>;
  for (const k of Object.keys(sent)) expect(Object.keys(s.properties)).toContain(k);
  for (const r of s.required ?? []) expect(Object.keys(sent)).toContain(r);
}

/** Confere se a rota (método + caminho com ids reais) existe no openapi, com os ids no lugar dos parâmetros. */
function expectRouteInSpec(method: string, path: string) {
  const hit = Object.entries(paths).find(([tpl, ops]) => {
    const re = new RegExp("^" + tpl.replace(/\{[^}]+\}/g, "[^/]+") + "$");
    return re.test(path) && method.toLowerCase() in ops;
  });
  expect(hit, `${method} ${path} não está no openapi`).toBeDefined();
}

describe("schemas de resposta batem com o openapi", () => {
  it("Connection = ConnectionOut", () => {
    expect(keys(ConnectionSchema.shape)).toEqual(keys(schemas.ConnectionOut.properties));
  });
  it("Balance = BalanceOut", () => {
    expect(keys(BalanceSchema.shape)).toEqual(keys(schemas.BalanceOut.properties));
  });
  it("validação de chave = KeyCheckOut", () => {
    expect(keys(ApiKeyValidationSchema.shape)).toEqual(keys(schemas.KeyCheckOut.properties));
  });
  it("resultado de extrato = StatementImportOut", () => {
    expect(keys(StatementImportResultSchema.shape)).toEqual(keys(schemas.StatementImportOut.properties));
  });
});

describe("corpos e rotas enviados pelo cliente batem com o openapi", () => {
  it("criar conexão por chave só leitura", async () => {
    await api.createApiKeyConnection("real", { institution: "binance", label: "Binance leitura", api_key: "k".repeat(20), api_secret: "s".repeat(20) });
    const c = calls.at(-1)!;
    expect(c.method).toBe("POST");
    expectRouteInSpec(c.method, c.path);
    expectBodyMatches(c.body, "ConnectionCreate");
    expect((c.body as { kind: string }).kind).toBe("readonly_key");
  });

  it("validar chave", async () => {
    await api.validateApiKey("real", { institution: "binance", api_key: "k".repeat(20), api_secret: "s".repeat(20) });
    const c = calls.at(-1)!;
    expectRouteInSpec(c.method, c.path);
    expectBodyMatches(c.body, "KeyValidationIn");
  });

  it("consentimento Open Finance", async () => {
    await expect(api.startOpenFinance("real", "nubank")).rejects.toThrow();
    const c = calls.at(-1)!;
    expectRouteInSpec(c.method, c.path);
    expectBodyMatches(c.body, "OpenFinanceConsentIn");
  });

  it("importar extrato CSV: cria a conexão de extrato e envia o conteúdo em JSON", async () => {
    const file = { name: "extrato.csv", size: 20, text: async () => "Data;Descrição;Valor\n01/11/2026;Pix;10,00" } as unknown as File;
    const mapping = { date: "Data", description: "Descrição", amount: "Valor", currency: null, date_format: "%d/%m/%Y" as const, delimiter: ";" as const };
    await api.importStatement("real", "nubank", "Nubank extrato", file, mapping);
    const [create, send] = calls.slice(-2);
    expectRouteInSpec(create.method, create.path);
    expectBodyMatches(create.body, "ConnectionCreate");
    expect((create.body as { kind: string }).kind).toBe("statement");
    expectRouteInSpec(send.method, send.path);
    expect(send.path).toBe(`/v1/connections/${CONN_ID}/statement`);
    expectBodyMatches(send.body, "StatementImportIn");
    expectBodyMatches((send.body as { mapping: object }).mapping, "CsvMappingIn");
  });

  it("apagar conexão", async () => {
    await api.deleteConnection("real", CONN_ID);
    const c = calls.at(-1)!;
    expect(c.method).toBe("DELETE");
    expectRouteInSpec(c.method, c.path);
  });

  it("nenhum corpo enviado contém campo de senha de banco", async () => {
    await api.createApiKeyConnection("real", { institution: "binance", label: "x", api_key: "k".repeat(20), api_secret: "s".repeat(20) });
    for (const c of calls) expect(JSON.stringify(c.body ?? {})).not.toMatch(/senha|password/i);
  });
});
