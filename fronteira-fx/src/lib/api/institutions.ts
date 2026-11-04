/**
 * Cadastro de instituições (`GET /v1/institutions`, `data/institutions.json` no backend).
 * Todo número traz `source_url` e `checked_at`; `value: null` quer dizer "não confirmado", nunca zero.
 */
import { z } from "zod";
import { DecimalString, CurrencySchema } from "./schemas";

export const SourcedFigureSchema = z.object({
  value: DecimalString.nullable(),
  currency: z.string().nullable(),
  source_url: z.string().nullable(),
  checked_at: z.string().nullable(),
  note: z.string().nullable(),
});

export const InstitutionSchema = z.object({
  id: z.string(),
  name: z.string(),
  country: z.enum(["BR", "PY", "INT"]),
  kind: z.enum(["bank", "fintech", "wallet", "broker"]),
  status: z.enum(["active", "discontinued"]),
  discontinued_note: z.string().nullable(),
  currencies_held: z.array(z.string()).nullable(),
  opens_remotely: z.boolean().nullable(),
  requires: z.string().nullable(),
  api: z.enum(["none", "pf", "pj_contract"]).nullable(),
  api_source_url: z.string().nullable(),
  source_url: z.string().nullable(),
  checked_at: z.string().nullable(),
  fx_cost: z.object({
    spread_pct: SourcedFigureSchema,
    iof_pct: SourcedFigureSchema,
    fee_pct: SourcedFigureSchema,
    fee_fixed: SourcedFigureSchema,
  }),
});

export type Institution = z.infer<typeof InstitutionSchema>;
export type SourcedFigure = z.infer<typeof SourcedFigureSchema>;

const ACCOUNT_CURRENCIES: readonly string[] = CurrencySchema.options;

/** Moedas do cadastro que o app sabe representar (BRL, USD, PYG). Vazio quando não confirmadas. */
export function institutionCurrencies(inst: Institution): string[] {
  return (inst.currencies_held ?? []).filter((c) => ACCOUNT_CURRENCIES.includes(c));
}

/** "2026-11-04" → "04/11/2026"; data ausente ou malformada → null (o selo mostra "sem data"). */
export function formatCheckedAt(iso: string | null): string | null {
  const m = iso?.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  return m ? `${m[3]}/${m[2]}/${m[1]}` : null;
}

/** Nome do domínio da fonte para o selo (ex.: "wise.com"); null se a URL não for válida. */
export function sourceHost(url: string | null): string | null {
  if (!url) return null;
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return null;
  }
}

/** Texto do selo "fonte": domínio e data. Null quando a figura não tem fonte confirmada. */
export function sourceLabel(fig: SourcedFigure): string | null {
  const host = sourceHost(fig.source_url);
  const date = formatCheckedAt(fig.checked_at);
  if (!host || !date) return null;
  return `fonte: ${host} · ${date}`;
}
