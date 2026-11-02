import type { Account, AccountInput } from "@/lib/api/types";
import { parseDecimalPtBR } from "@/lib/format";

export interface AccountForm {
  institution: string;
  label: string;
  currency: string;
  kind: string;
  location: string;
  balance_free: string;
}

export const EMPTY_ACCOUNT_FORM: AccountForm = { institution: "", label: "", currency: "USD", kind: "bank", location: "digital", balance_free: "0" };

/** Mensagem de erro em pt-BR ou null quando o formulário está pronto para enviar. */
export function validateAccountForm(f: AccountForm): string | null {
  if (!f.institution.trim()) return "Informe a instituição.";
  if (!f.label.trim()) return "Informe o rótulo da conta.";
  if (parseDecimalPtBR(f.balance_free) === null) return "Saldo inválido: use números como 5.000,50.";
  return null;
}

/** String decimal da API ("7.125") → texto para um campo pt-BR ("7,125"); `parseDecimalPtBR` lê de volta o mesmo valor. */
export function canonicalToPtBR(value: string): string {
  return value.replace(".", ",");
}

/** Dinheiro sai como string decimal canônica (nunca float). */
export function accountInputFromForm(f: AccountForm): AccountInput {
  return {
    institution: f.institution.trim(),
    label: f.label.trim(),
    currency: f.currency as Account["currency"],
    kind: f.kind as Account["kind"],
    location: f.location as Account["location"],
    balance_free: parseDecimalPtBR(f.balance_free) ?? "0",
    balance_reserved: "0",
    balance_in_transit: "0",
  };
}
