import { describe, expect, it } from "vitest";
import { accountInputFromForm, canonicalToPtBR, EMPTY_ACCOUNT_FORM, validateAccountForm } from "./accounts-form";

describe("formulário de conta (dinheiro como string decimal)", () => {
  const form = { ...EMPTY_ACCOUNT_FORM, institution: " banco-demo-py ", label: "Conta PYG", currency: "PYG", kind: "bank", location: "ASU", balance_free: "5.000,50" };
  it("aceita pt-BR e devolve string decimal canônica", () => {
    expect(validateAccountForm(form)).toBeNull();
    expect(accountInputFromForm(form)).toEqual({ institution: "banco-demo-py", label: "Conta PYG", currency: "PYG", kind: "bank", location: "ASU", balance_free: "5000.5", balance_reserved: "0", balance_in_transit: "0" });
  });
  it("rejeita saldo inválido e campos vazios", () => {
    expect(validateAccountForm({ ...form, balance_free: "abc" })).toMatch(/saldo/i);
    expect(validateAccountForm({ ...form, institution: "" })).toMatch(/instituição/i);
    expect(validateAccountForm({ ...form, label: "  " })).toMatch(/rótulo/i);
  });
});

describe("canonicalToPtBR (semente dos campos de edição)", () => {
  it("string decimal da API vira texto pt-BR que o parser lê de volta igual", () => {
    for (const v of ["7.125", "1500.000", "25000", "0.5", "-12.75", "0"]) {
      const typed = canonicalToPtBR(v);
      expect(typed).not.toContain(".");
      expect(Number(accountInputFromForm({ ...EMPTY_ACCOUNT_FORM, institution: "x", label: "y", balance_free: typed }).balance_free)).toBe(Number(v));
    }
    expect(canonicalToPtBR("7.125")).toBe("7,125");
  });
});
