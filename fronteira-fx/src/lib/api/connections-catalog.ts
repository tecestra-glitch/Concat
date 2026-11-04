/**
 * Catálogo de instituições da tela de conexões, agrupado. Cada instituição lista os caminhos de conexão que a tela
 * oferece; "Saldo manual" está sempre disponível (leva para Contas e cartões). A disponibilidade real de Open
 * Finance depende do agregador configurado no servidor, e isso vem de `aggregator_configured`.
 */

export type ConnectionPath = "open_finance" | "api_key_readonly" | "statement_import" | "manual_balance";

export interface CatalogInstitution {
  id: string;
  name: string;
  /** Caminhos de conexão que se aplicam (sem o saldo manual, que é sempre oferecido). */
  paths: Exclude<ConnectionPath, "manual_balance">[];
}

export interface CatalogGroup {
  id: string;
  title: string;
  description: string;
  institutions: CatalogInstitution[];
}

export const CATALOG: CatalogGroup[] = [
  {
    id: "bancos-brasil",
    title: "Bancos do Brasil",
    description: "Open Finance quando o agregador estiver configurado; senão, extrato ou saldo manual.",
    institutions: [
      { id: "nubank", name: "Nubank", paths: ["open_finance", "statement_import"] },
      { id: "itau", name: "Itaú", paths: ["open_finance", "statement_import"] },
      { id: "inter", name: "Inter", paths: ["open_finance", "statement_import"] },
      { id: "c6", name: "C6 Bank", paths: ["open_finance", "statement_import"] },
      { id: "bradesco", name: "Bradesco", paths: ["open_finance", "statement_import"] },
      { id: "santander", name: "Santander", paths: ["open_finance", "statement_import"] },
      { id: "bb", name: "Banco do Brasil", paths: ["open_finance", "statement_import"] },
    ],
  },
  {
    id: "contas-globais",
    title: "Contas globais",
    description: "Contas em moeda estrangeira. Chave de leitura quando o banco oferece; extrato ou saldo manual sempre.",
    institutions: [
      { id: "nomad", name: "Nomad", paths: ["statement_import"] },
      { id: "revolut", name: "Revolut", paths: ["api_key_readonly", "statement_import"] },
      { id: "wise", name: "Wise", paths: ["api_key_readonly", "statement_import"] },
      { id: "global66", name: "Global66", paths: ["statement_import"] },
    ],
  },
  {
    id: "paraguai",
    title: "Paraguai",
    description: "Bancos paraguaios: a conexão é por extrato ou saldo manual.",
    institutions: [
      { id: "itau-py", name: "Itaú Paraguai", paths: ["statement_import"] },
      { id: "basa", name: "Basa", paths: ["statement_import"] },
      { id: "familiar", name: "Familiar", paths: ["statement_import"] },
      { id: "continental", name: "Continental", paths: ["statement_import"] },
      { id: "sudameris", name: "Sudameris", paths: ["statement_import"] },
    ],
  },
  {
    id: "cripto",
    title: "Corretoras de cripto",
    description: "Chave de API só leitura: a chave não pode operar nem sacar. O app recusa chave com essas permissões.",
    institutions: [
      { id: "binance", name: "Binance", paths: ["api_key_readonly", "statement_import"] },
      { id: "kraken", name: "Kraken", paths: ["api_key_readonly", "statement_import"] },
      { id: "foxbit", name: "Foxbit", paths: ["api_key_readonly", "statement_import"] },
      { id: "mercado-bitcoin", name: "Mercado Bitcoin", paths: ["api_key_readonly", "statement_import"] },
      { id: "okx", name: "OKX", paths: ["api_key_readonly", "statement_import"] },
    ],
  },
];

export const PATH_LABEL: Record<ConnectionPath, string> = {
  open_finance: "Autorizar pelo Open Finance",
  api_key_readonly: "Chave de API só leitura",
  statement_import: "Importar extrato (CSV/OFX)",
  manual_balance: "Saldo manual",
};

/** Todas as instituições do catálogo, achatadas, na ordem de exibição. */
export function allInstitutions(groups: CatalogGroup[] = CATALOG): CatalogInstitution[] {
  return groups.flatMap((g) => g.institutions);
}

/** Caminhos oferecidos para uma instituição: os do catálogo mais o saldo manual, sempre por último. */
export function pathsFor(inst: CatalogInstitution): ConnectionPath[] {
  return [...inst.paths, "manual_balance"];
}
