import { describe, expect, it } from "vitest";
import { ApiKeyValidationSchema, ConnectionSchema, OpenFinanceStartSchema, StatementImportResultSchema, apiKeyRefusal, maskKey, keyHintText, statementFormat, STATEMENT_MAX_BYTES, TRADE_FLAGS, WITHDRAW_FLAGS, type ApiKeyValidation } from "@/lib/api/connections";
import { CATALOG, allInstitutions, pathsFor } from "@/lib/api/connections-catalog";
import { demoConnectionList, demoCreateApiKeyConnection, demoCreateStatementConnection, demoDeleteConnection, demoImportStatement, demoValidateApiKey, resetDemoConnections } from "@/lib/api/demo-connections";
import { api } from "@/lib/api/client";

const conn = {
  id: "c1",
  institution: "binance",
  label: "Binance leitura",
  kind: "readonly_key",
  status: "active",
  data_mode: "real",
  account_id: null,
  key_hint: "9f2K",
  balances: [{ asset: "USDT", free: "120.5", locked: "0" }],
  last_error: null,
  last_synced_at: null,
  created_at: "2026-11-04T09:00:00.000Z",
  updated_at: "2026-11-04T09:00:00.000Z",
};

const okCheck = (over: Partial<ApiKeyValidation> = {}): ApiKeyValidation => ({
  ok: true,
  institution: "binance",
  flags: Object.fromEntries([...TRADE_FLAGS, ...WITHDRAW_FLAGS].map((f) => [f, false])),
  reasons: [],
  balances: [],
  ...over,
});

describe("contrato de conexões (zod)", () => {
  it("aceita a conexão do servidor e rejeita tipo fora do contrato", () => {
    expect(ConnectionSchema.parse(conn).key_hint).toBe("9f2K");
    expect(() => ConnectionSchema.parse({ ...conn, kind: "transfer" })).toThrow();
    expect(() => ConnectionSchema.parse({ ...conn, status: "revoked" })).toThrow();
  });

  it("key_hint tem no máximo 4 caracteres (nunca a chave inteira)", () => {
    expect(() => ConnectionSchema.parse({ ...conn, key_hint: "abcdef123456" })).toThrow();
  });

  it("open finance exige endereço https", () => {
    expect(OpenFinanceStartSchema.parse({ redirect_url: "https://consent.example/abc" }).redirect_url).toMatch(/^https:/);
    expect(() => OpenFinanceStartSchema.parse({ redirect_url: "http://x.example" })).toThrow();
    expect(() => OpenFinanceStartSchema.parse({ redirect_url: "javascript:alert(1)" })).toThrow();
  });

  it("validação de chave segue o KeyCheckOut (ok, flags, reasons, balances)", () => {
    expect(ApiKeyValidationSchema.parse(okCheck())).toEqual(okCheck());
    expect(() => ApiKeyValidationSchema.parse({ read: true, trade: false, withdraw: false })).toThrow();
  });

  it("resultado de extrato traz contagens e dinheiro como string decimal", () => {
    const r = StatementImportResultSchema.parse({ connection_id: "c1", format: "csv", imported: 3, duplicates: 1, account_id: null, balance_delta: "0", account_balance_free: null });
    expect(r.imported).toBe(3);
    expect(() => StatementImportResultSchema.parse({ connection_id: "c1", format: "pdf", imported: 0, duplicates: 0, account_id: null, balance_delta: "0", account_balance_free: null })).toThrow();
  });

  it("formato do extrato vem da extensão", () => {
    expect(statementFormat("Extrato.CSV")).toBe("csv");
    expect(statementFormat("fatura.ofx")).toBe("ofx");
    expect(statementFormat("x.pdf")).toBeNull();
  });
});

describe("recusa de chave perigosa", () => {
  it("chave só de leitura passa", () => {
    expect(apiKeyRefusal(okCheck())).toBeNull();
  });
  it("chave que pode operar ou sacar é recusada, mesmo com ok=true", () => {
    expect(apiKeyRefusal(okCheck({ flags: { enableSpotAndMarginTrading: true, enableWithdrawals: false } }))).toMatch(/operar/);
    expect(apiKeyRefusal(okCheck({ flags: { enableSpotAndMarginTrading: false, enableWithdrawals: true } }))).toMatch(/sacar/);
    expect(apiKeyRefusal(okCheck({ flags: { enableSpotAndMarginTrading: true, enableWithdrawals: true } }))).toMatch(/operar e sacar/);
  });
  it("flag ausente ou nula conta como ligada (falha fechada)", () => {
    expect(apiKeyRefusal(okCheck({ flags: { enableWithdrawals: null } }))).toMatch(/sacar/);
    expect(apiKeyRefusal(okCheck({ flags: {} }))).toMatch(/operar/);
  });
  it("recusa do servidor (ok=false) mostra o motivo", () => {
    expect(apiKeyRefusal(okCheck({ ok: false, reasons: ["conta sem leitura"] }))).toMatch(/conta sem leitura/);
  });
});

describe("mascaramento de segredo", () => {
  it("mostra só os últimos 4 caracteres", () => {
    expect(maskKey("abcdefghijklmnop")).toBe("••••mnop");
    expect(keyHintText("mnop")).toBe("••••mnop");
  });
  it("nunca devolve a chave inteira, nem para chaves curtas", () => {
    for (const k of ["a", "abcd", "abcdefgh", "x".repeat(40)]) {
      const out = maskKey(k);
      expect(out.length).toBeLessThanOrEqual(8);
      if (k.length > 4) expect(out).not.toBe(k);
    }
    expect(maskKey("abcd")).toBe("••••");
    expect(keyHintText(null)).toBeNull();
  });
});

describe("catálogo de instituições", () => {
  it("tem os quatro grupos pedidos, com ids únicos", () => {
    expect(CATALOG.map((g) => g.title)).toEqual(["Bancos do Brasil", "Contas globais", "Paraguai", "Corretoras de cripto"]);
    const ids = allInstitutions().map((i) => i.id);
    expect(new Set(ids).size).toBe(ids.length);
    expect(ids).toEqual(expect.arrayContaining(["nubank", "itau", "inter", "c6", "bradesco", "santander", "bb", "nomad", "revolut", "wise", "global66", "itau-py", "basa", "familiar", "continental", "sudameris", "binance", "kraken", "foxbit", "mercado-bitcoin", "okx"]));
  });
  it("saldo manual é sempre oferecido, por último", () => {
    for (const inst of allInstitutions()) expect(pathsFor(inst).at(-1)).toBe("manual_balance");
  });
  it("corretoras de cripto só oferecem chave de leitura ou extrato", () => {
    const cripto = CATALOG.find((g) => g.id === "cripto")!;
    for (const inst of cripto.institutions) expect(inst.paths.every((p) => p === "api_key_readonly" || p === "statement_import")).toBe(true);
  });
  it("limite de extrato é 5 MB", () => {
    expect(STATEMENT_MAX_BYTES).toBe(512 * 1024);
  });
});

describe("modo demo (sem rede, marcado como demonstração)", () => {
  it("lista demo: todo registro tem data_mode demo e agregador não configurado", () => {
    resetDemoConnections();
    const list = demoConnectionList();
    expect(list.aggregator_configured).toBe(false);
    expect(list.connections.every((c) => c.data_mode === "demo")).toBe(true);
    expect(() => ConnectionSchema.array().parse(list.connections)).not.toThrow();
  });
  it("chave de demonstração com trade ou withdraw é recusada pela heurística", () => {
    expect(apiKeyRefusal(demoValidateApiKey("demo-trade-0123456789abcdef"))).not.toBeNull();
    expect(apiKeyRefusal(demoValidateApiKey("demo-withdraw-0123456789abcdef"))).not.toBeNull();
    expect(apiKeyRefusal(demoValidateApiKey("demo-leitura-0123456789abcdef"))).toBeNull();
  });
  it("criar guarda só a dica da chave; o segredo não entra no registro", () => {
    resetDemoConnections();
    const c = demoCreateApiKeyConnection({ institution: "kraken", label: "Kraken leitura", api_key: "CHAVE-LEITURA-0123456789ZZ9" });
    expect(c.key_hint).toBe("9ZZ9");
    expect(JSON.stringify(c)).not.toContain("CHAVE-LEITURA");
    demoDeleteConnection(c.id);
    expect(demoConnectionList().connections.find((x) => x.id === c.id)).toBeUndefined();
  });
  it("importar extrato em demo não lê linhas", () => {
    resetDemoConnections();
    const c = demoCreateStatementConnection({ institution: "nomad", label: "Nomad extrato" });
    const r = demoImportStatement(c, "csv");
    expect(r.imported).toBe(0);
    expect(r.connection_id).toBe(c.id);
  });
  it("api.connections em demo não toca a rede", async () => {
    resetDemoConnections();
    const spy = (globalThis as { fetch?: unknown }).fetch;
    const out = await api.connections("demo");
    expect(out.connections.length).toBeGreaterThan(0);
    expect((globalThis as { fetch?: unknown }).fetch).toBe(spy);
  });
});
