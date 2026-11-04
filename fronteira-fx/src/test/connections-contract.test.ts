import { describe, expect, it } from "vitest";
import { ApiKeyValidationSchema, ConnectionListSchema, OpenFinanceStartSchema, apiKeyRefusal, maskKey, keyHintText, STATEMENT_MAX_BYTES } from "@/lib/api/connections";
import { CATALOG, allInstitutions, pathsFor } from "@/lib/api/connections-catalog";
import { demoConnectionList, demoCreateApiKeyConnection, demoDeleteConnection, demoImportStatement, demoValidateApiKey, resetDemoConnections } from "@/lib/api/demo-connections";
import { api } from "@/lib/api/client";

const conn = {
  id: "c1",
  institution_id: "binance",
  institution_name: "Binance",
  method: "api_key_readonly",
  status: "active",
  key_hint: "9f2K",
  created_at: "2026-11-04T09:00:00.000Z",
  last_sync_at: null,
  data_mode: "real",
};

describe("contrato de conexões (zod)", () => {
  it("aceita a lista do servidor e rejeita método fora do contrato", () => {
    expect(ConnectionListSchema.parse({ aggregator_configured: false, connections: [conn] }).connections[0].key_hint).toBe("9f2K");
    expect(() => ConnectionListSchema.parse({ aggregator_configured: false, connections: [{ ...conn, method: "transfer" }] })).toThrow();
  });

  it("key_hint tem no máximo 4 caracteres (nunca a chave inteira)", () => {
    expect(() => ConnectionListSchema.parse({ aggregator_configured: true, connections: [{ ...conn, key_hint: "abcdef123456" }] })).toThrow();
  });

  it("open finance exige endereço https", () => {
    expect(OpenFinanceStartSchema.parse({ redirect_url: "https://consent.example/abc" }).redirect_url).toMatch(/^https:/);
    expect(() => OpenFinanceStartSchema.parse({ redirect_url: "http://x.example" })).toThrow();
    expect(() => OpenFinanceStartSchema.parse({ redirect_url: "javascript:alert(1)" })).toThrow();
  });

  it("validação de chave exige os três campos booleanos", () => {
    expect(ApiKeyValidationSchema.parse({ read: true, trade: false, withdraw: false })).toEqual({ read: true, trade: false, withdraw: false });
    expect(() => ApiKeyValidationSchema.parse({ read: true, trade: false })).toThrow();
  });
});

describe("recusa de chave perigosa", () => {
  it("chave só de leitura passa", () => {
    expect(apiKeyRefusal({ read: true, trade: false, withdraw: false })).toBeNull();
  });
  it("chave que pode operar ou sacar é recusada", () => {
    expect(apiKeyRefusal({ read: true, trade: true, withdraw: false })).toMatch(/operar/);
    expect(apiKeyRefusal({ read: true, trade: false, withdraw: true })).toMatch(/sacar/);
    expect(apiKeyRefusal({ read: true, trade: true, withdraw: true })).toMatch(/operar e sacar/);
  });
  it("chave sem leitura é recusada", () => {
    expect(apiKeyRefusal({ read: false, trade: false, withdraw: false })).toMatch(/leitura/);
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
    expect(STATEMENT_MAX_BYTES).toBe(5 * 1024 * 1024);
  });
});

describe("modo demo (sem rede, marcado como demonstração)", () => {
  it("lista demo: todo registro tem data_mode demo e agregador não configurado", () => {
    resetDemoConnections();
    const list = demoConnectionList();
    expect(list.aggregator_configured).toBe(false);
    expect(list.connections.every((c) => c.data_mode === "demo")).toBe(true);
    expect(() => ConnectionListSchema.parse(list)).not.toThrow();
  });
  it("chave de demonstração com trade ou withdraw é recusada pela heurística", () => {
    expect(apiKeyRefusal(demoValidateApiKey("demo-trade-0123456789abcdef"))).not.toBeNull();
    expect(apiKeyRefusal(demoValidateApiKey("demo-leitura-0123456789abcdef"))).toBeNull();
  });
  it("criar guarda só a dica da chave; o segredo não entra no registro", () => {
    resetDemoConnections();
    const c = demoCreateApiKeyConnection({ institution_id: "kraken", institution_name: "Kraken", api_key: "CHAVE-LEITURA-0123456789ZZ9" });
    expect(c.key_hint).toBe("9ZZ9");
    expect(JSON.stringify(c)).not.toContain("CHAVE-LEITURA");
    demoDeleteConnection(c.id);
    expect(demoConnectionList().connections.find((x) => x.id === c.id)).toBeUndefined();
  });
  it("importar extrato em demo não lê linhas", () => {
    resetDemoConnections();
    const r = demoImportStatement({ institution_id: "nomad", institution_name: "Nomad" });
    expect(r.rows_read).toBe(0);
    expect(r.connection.status).toBe("pending");
  });
  it("api.connections em demo não toca a rede", async () => {
    resetDemoConnections();
    const spy = (globalThis as { fetch?: unknown }).fetch;
    const out = await api.connections("demo");
    expect(out.connections.length).toBeGreaterThan(0);
    expect((globalThis as { fetch?: unknown }).fetch).toBe(spy);
  });
});
