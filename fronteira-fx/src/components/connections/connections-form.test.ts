import { describe, expect, it } from "vitest";
import { EMPTY_API_KEY_FORM, hasApiKeyErrors, statementFileError, validateApiKeyForm } from "./connections-form";

const good = { apiKey: "AbCdEf0123456789xyz", apiSecret: "SeGrEdO0123456789abc", readOnlyConfirmed: true };

describe("formulário de chave de API", () => {
  it("aceita chave e segredo bem formados com a confirmação de leitura", () => {
    expect(hasApiKeyErrors(validateApiKeyForm(good))).toBe(false);
  });
  it("exige os dois campos e a confirmação", () => {
    const e = validateApiKeyForm(EMPTY_API_KEY_FORM);
    expect(e.apiKey).toMatch(/Informe/);
    expect(e.apiSecret).toMatch(/Informe/);
    expect(e.readOnlyConfirmed).toMatch(/Confirme/);
  });
  it("recusa chave curta, longa ou com espaço", () => {
    expect(validateApiKeyForm({ ...good, apiKey: "curta" }).apiKey).toMatch(/curto/);
    expect(validateApiKeyForm({ ...good, apiKey: "x".repeat(300) }).apiKey).toMatch(/longo/);
    expect(validateApiKeyForm({ ...good, apiKey: "AbCdEf 0123456789xyz" }).apiKey).toMatch(/sem espaços/);
  });
  it("recusa caracteres fora de token (ex.: tags HTML)", () => {
    expect(validateApiKeyForm({ ...good, apiSecret: "<script>alert(1)</script>0123" }).apiSecret).toMatch(/caracteres/);
  });
  it("mensagens de erro nunca repetem o valor digitado", () => {
    const secret = "segredo-muito-secreto!!";
    const e = validateApiKeyForm({ ...good, apiSecret: secret });
    expect(JSON.stringify(e)).not.toContain(secret);
  });
});

describe("arquivo de extrato", () => {
  it("aceita csv e ofx dentro do limite", () => {
    expect(statementFileError({ name: "extrato.CSV", size: 1200 })).toBeNull();
    expect(statementFileError({ name: "fatura.ofx", size: 1200 })).toBeNull();
  });
  it("recusa outra extensão, vazio, grande demais ou ausente", () => {
    expect(statementFileError({ name: "x.pdf", size: 10 })).toMatch(/csv|ofx/);
    expect(statementFileError({ name: "x.csv", size: 0 })).toMatch(/vazio/);
    expect(statementFileError({ name: "x.csv", size: 600 * 1024 })).toMatch(/512 KB/);
    expect(statementFileError(null)).toMatch(/Escolha/);
  });
});
