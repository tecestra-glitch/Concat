/**
 * Premissas do cruzamento (somente leitura): espelho de `backend/src/fronteira_fx/data/transport.json` e
 * `rails.json`. Um teste (`src/test/premissas.test.ts`) confere que os dois lados batem. Custo `null` = não
 * verificado: a interface mostra "não verificado", nunca zero.
 */

export interface PremissaRoute {
  id: string;
  from_city: string;
  to_city: string;
  mode: string;
  cost: null;
  minutes: number;
  border: boolean;
  symmetric: boolean;
  source_url: string | null;
  checked_at: string | null;
  verified: boolean;
}

export interface PremissaRail {
  id: string;
  from: string;
  to: string;
  currency: string;
  to_currency: string;
  fee_fixed: null;
  fee_pct: null;
  iof_pct: null;
  minutes: number;
  min_amount: null;
  max_amount: null;
  source_url: string | null;
  checked_at: string | null;
  verified: boolean;
}

export const PREMISSAS_TRANSPORT: PremissaRoute[] = [
  { id: "foz-cde", from_city: "FOZ", to_city: "CDE", mode: "car", cost: null, minutes: 40, border: true, symmetric: true, source_url: null, checked_at: null, verified: false },
  { id: "cde-asu", from_city: "CDE", to_city: "ASU", mode: "bus", cost: null, minutes: 240, border: false, symmetric: true, source_url: null, checked_at: null, verified: false },
  { id: "asu-pjc", from_city: "ASU", to_city: "PJC", mode: "bus", cost: null, minutes: 540, border: false, symmetric: true, source_url: null, checked_at: null, verified: false },
  { id: "pjc-ppo", from_city: "PJC", to_city: "PPO", mode: "car", cost: null, minutes: 15, border: true, symmetric: true, source_url: null, checked_at: null, verified: false },
  { id: "cde-enc", from_city: "CDE", to_city: "ENC", mode: "bus", cost: null, minutes: 330, border: false, symmetric: true, source_url: null, checked_at: null, verified: false },
];

export const PREMISSAS_RAILS: PremissaRail[] = [
  { id: "pix-br-bank-revolut-brl", from: "br_bank", to: "revolut", currency: "BRL", to_currency: "BRL", fee_fixed: null, fee_pct: null, iof_pct: null, minutes: 5, min_amount: null, max_amount: null, source_url: null, checked_at: null, verified: false },
  { id: "br-bank-nomad-usd-conv", from: "br_bank", to: "nomad", currency: "BRL", to_currency: "USD", fee_fixed: null, fee_pct: null, iof_pct: null, minutes: 1440, min_amount: null, max_amount: null, source_url: null, checked_at: null, verified: false },
  { id: "nomad-revolut-usd", from: "nomad", to: "revolut", currency: "USD", to_currency: "USD", fee_fixed: null, fee_pct: null, iof_pct: null, minutes: 60, min_amount: null, max_amount: null, source_url: null, checked_at: null, verified: false },
  { id: "revolut-nomad-usd", from: "revolut", to: "nomad", currency: "USD", to_currency: "USD", fee_fixed: null, fee_pct: null, iof_pct: null, minutes: 60, min_amount: null, max_amount: null, source_url: null, checked_at: null, verified: false },
  { id: "sipap-py-bank-to-house-pyg", from: "py_bank", to: "exchange_house", currency: "PYG", to_currency: "PYG", fee_fixed: null, fee_pct: null, iof_pct: null, minutes: 30, min_amount: null, max_amount: null, source_url: null, checked_at: null, verified: false },
  { id: "deposito-house-to-py-bank-pyg", from: "exchange_house", to: "py_bank", currency: "PYG", to_currency: "PYG", fee_fixed: null, fee_pct: null, iof_pct: null, minutes: 120, min_amount: null, max_amount: null, source_url: null, checked_at: null, verified: false },
  { id: "saque-atm-py-bank-pyg", from: "py_bank", to: "cash", currency: "PYG", to_currency: "PYG", fee_fixed: null, fee_pct: null, iof_pct: null, minutes: 60, min_amount: null, max_amount: null, source_url: null, checked_at: null, verified: false },
  { id: "saque-atm-revolut-usd", from: "revolut", to: "cash", currency: "USD", to_currency: "USD", fee_fixed: null, fee_pct: null, iof_pct: null, minutes: 60, min_amount: null, max_amount: null, source_url: null, checked_at: null, verified: false },
  { id: "saque-atm-br-bank-brl", from: "br_bank", to: "cash", currency: "BRL", to_currency: "BRL", fee_fixed: null, fee_pct: null, iof_pct: null, minutes: 60, min_amount: null, max_amount: null, source_url: null, checked_at: null, verified: false },
];

/** Rótulo de confiança de uma premissa: sem verificação (ou sem fonte) nunca aparece como confirmada. */
export function premissaStatus(p: { verified: boolean; source_url: string | null; checked_at: string | null }): { verified: boolean; label: string; source: string } {
  return { verified: p.verified, label: p.verified ? "verificado" : "não verificado", source: p.source_url ?? "fonte não informada" };
}
