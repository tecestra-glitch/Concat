/**
 * Contrato de conexões de contas (`/v1/connections`). A fonte da verdade é `docs/api-contract.md` (seção
 * "Conexões de conta") e o openapi exportado do backend; `src/test/connections-openapi.test.ts` confere estes schemas
 * contra o openapi (campos, rotas e corpos enviados). Se o backend mudar, muda aqui no mesmo commit.
 *
 * Regras que valem para todo o módulo:
 * - o app NUNCA recebe, guarda ou mostra senha de banco. Segredo de API (`api_secret`) só sai do navegador no corpo
 *   de validação/criação e nunca volta na resposta;
 * - a resposta traz só `key_hint` (últimos 4 caracteres da chave pública), nunca a chave completa;
 * - a chave precisa ser só de leitura: uma chave que pode operar ou sacar é recusada aqui e no servidor;
 * - o conteúdo de extratos (CSV/OFX) é dado não confiável: o servidor lê, a tela só checa extensão e tamanho.
 */
import { z } from "zod";

export const ConnectionKindSchema = z.enum(["consent", "readonly_key", "statement", "manual"]);
export type ConnectionKind = z.infer<typeof ConnectionKindSchema>;

export const ConnectionStatusSchema = z.enum(["pending", "active", "error"]);
export type ConnectionStatus = z.infer<typeof ConnectionStatusSchema>;

export const ConnectionDataModeSchema = z.enum(["real", "simulation", "demo"]);

/** Saldo em string decimal (dinheiro nunca vira número na tela). */
export const BalanceSchema = z.object({
  asset: z.string(),
  free: z.string(),
  locked: z.string(),
});
export type Balance = z.infer<typeof BalanceSchema>;

/** `ConnectionOut` do servidor. `key_hint` tem no máximo 4 caracteres: nunca a chave inteira. */
export const ConnectionSchema = z.object({
  id: z.string(),
  institution: z.string(),
  label: z.string(),
  kind: ConnectionKindSchema,
  status: ConnectionStatusSchema,
  data_mode: ConnectionDataModeSchema,
  account_id: z.string().nullable(),
  key_hint: z.string().max(4).nullable(),
  balances: z.array(BalanceSchema).nullable(),
  last_error: z.string().nullable(),
  last_synced_at: z.string().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
});
export type Connection = z.infer<typeof ConnectionSchema>;

/**
 * Lista usada pela tela. `GET /v1/connections` devolve só a lista; o estado do agregador de Open Finance ainda não
 * é exposto pelo servidor, então a tela trata como não configurado (falha fechada) até existir esse campo.
 */
export const ConnectionListSchema = z.object({
  aggregator_configured: z.boolean(),
  connections: z.array(ConnectionSchema),
});
export type ConnectionList = z.infer<typeof ConnectionListSchema>;

/** `KeyCheckOut` de `POST /v1/connections/validate-key`: nada é gravado. `ok:false` vem com `reasons`. */
export const ApiKeyValidationSchema = z.object({
  ok: z.boolean(),
  institution: z.string(),
  flags: z.record(z.string(), z.boolean().nullable()),
  reasons: z.array(z.string()),
  balances: z.array(BalanceSchema),
});
export type ApiKeyValidation = z.infer<typeof ApiKeyValidationSchema>;

/** Corpo de validação e de criação de chave só leitura. */
export const ApiKeyInputSchema = z.object({
  institution: z.string().min(1),
  api_key: z.string().min(16).max(256),
  api_secret: z.string().min(16).max(256),
});
export type ApiKeyInput = z.infer<typeof ApiKeyInputSchema>;

/**
 * Início do consentimento Open Finance. O servidor ainda não tem caminho de sucesso (responde 503 sem agregador e 501
 * com agregador sem integração); quando existir, o endereço de consentimento vai aqui. Só aceita https.
 */
export const OpenFinanceStartSchema = z.object({
  redirect_url: z.string().refine((u) => {
    try {
      return new URL(u).protocol === "https:";
    } catch {
      return false;
    }
  }, "endereço de consentimento inválido"),
});
export type OpenFinanceStart = z.infer<typeof OpenFinanceStartSchema>;

/** Formato aceito de chave e segredo: caracteres de token comuns, sem espaços (copiar e colar costuma trazer espaço). */
export const API_TOKEN_PATTERN = /^[A-Za-z0-9_\-+/=.]+$/;

export const STATEMENT_FORMATS = ["csv", "ofx"] as const;
export type StatementFormat = (typeof STATEMENT_FORMATS)[number];

/** `StatementImportOut` de `POST /v1/connections/{id}/statement`. */
export const StatementImportResultSchema = z.object({
  connection_id: z.string(),
  format: z.enum(STATEMENT_FORMATS),
  imported: z.number().int().nonnegative(),
  duplicates: z.number().int().nonnegative(),
  account_id: z.string().nullable(),
  balance_delta: z.string(),
  account_balance_free: z.string().nullable(),
});
export type StatementImportResult = z.infer<typeof StatementImportResultSchema>;

/** Mapeamento de colunas do CSV (`CsvMappingIn`). Obrigatório para CSV; OFX não usa. */
export const CSV_DATE_FORMATS = ["%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d.%m.%Y"] as const;
export const CSV_DELIMITERS = [",", ";", "\t"] as const;

export const CsvMappingSchema = z.object({
  date: z.string().min(1).max(64),
  description: z.string().min(1).max(64),
  amount: z.string().min(1).max(64),
  currency: z.string().max(64).nullable().optional(),
  date_format: z.enum(CSV_DATE_FORMATS),
  delimiter: z.enum(CSV_DELIMITERS),
});
export type CsvMapping = z.infer<typeof CsvMappingSchema>;

/** Limite de texto do extrato (`content`), igual ao do servidor: 512 KiB. */
export const STATEMENT_MAX_CHARS = 512 * 1024;

/** Corpo de `POST /v1/connections/{id}/statement` (JSON, sem arquivo multipart). */
export const StatementImportInSchema = z.object({
  format: z.enum(STATEMENT_FORMATS),
  content: z.string().min(1).max(STATEMENT_MAX_CHARS),
  mapping: CsvMappingSchema.nullable().optional(),
  default_currency: z.enum(["BRL", "USD", "PYG"]).nullable().optional(),
});
export type StatementImportIn = z.infer<typeof StatementImportInSchema>;

/** Dica de chave de uma conexão: os 4 últimos caracteres. `null` quando não há chave. */
export function keyTail(key: string): string | null {
  const v = key.trim();
  return v.length >= 8 ? v.slice(-4) : null;
}

/** Mostra só os últimos 4 caracteres. Nunca devolve a chave inteira, nem para chaves curtas. */
export function maskKey(key: string): string {
  const tail = keyTail(key);
  return tail ? `••••${tail}` : "••••";
}

/** Atalho para a dica de chave guardada na conexão (vem do servidor como `key_hint`). */
export function keyHintText(hint: string | null): string | null {
  return hint ? `••••${hint}` : null;
}

/** Flags da corretora que, ligadas, dão poder de operar. Ausente ou nulo conta como ligado (regra do servidor). */
export const TRADE_FLAGS = ["enableSpotAndMarginTrading", "enableMargin", "enableFutures", "enableVanillaOptions", "enablePortfolioMarginTrading"] as const;
/** Flags que, ligadas, dão poder de sacar ou transferir. */
export const WITHDRAW_FLAGS = ["enableWithdrawals", "enableInternalTransfer", "permitsUniversalTransfer"] as const;

const flagOn = (flags: ApiKeyValidation["flags"], name: string): boolean => flags[name] !== false;

/**
 * Mensagem de recusa para uma chave que não serve como só leitura, ou `null` quando a chave passou. A regra é
 * dupla: a tela recusa antes de salvar e o servidor recusa de novo (defesa em profundidade).
 */
export function apiKeyRefusal(v: ApiKeyValidation): string | null {
  const trade = TRADE_FLAGS.some((f) => flagOn(v.flags, f));
  const withdraw = WITHDRAW_FLAGS.some((f) => flagOn(v.flags, f));
  if (trade && withdraw) return "Esta chave pode operar e sacar. O Fronteira FX recusa chaves assim. Crie outra só com leitura.";
  if (trade) return "Esta chave pode operar (negociar). O Fronteira FX recusa chaves assim. Crie outra só com leitura.";
  if (withdraw) return "Esta chave pode sacar. O Fronteira FX recusa chaves assim. Crie outra só com leitura.";
  if (!v.ok) return v.reasons.length > 0 ? v.reasons.slice(0, 3).join(" ") : "A instituição não confirmou que a chave é só de leitura.";
  return null;
}

/** Caminhos da API (sem a base `/api/fx`). Modo entra pela query, como no resto do cliente. */
export const CONNECTIONS_PATH = "/v1/connections";
export const connectionPath = (id: string): string => `${CONNECTIONS_PATH}/${encodeURIComponent(id)}`;

/** Extensões e tamanho máximo de extrato aceitos pela tela (o servidor valida de novo: 512 KiB e 5000 lançamentos). */
export const STATEMENT_EXTENSIONS = [".csv", ".ofx"] as const;
export const STATEMENT_MAX_BYTES = 512 * 1024;

/** Formato do arquivo pela extensão, ou `null` quando não é aceito. */
export function statementFormat(fileName: string): StatementFormat | null {
  const lower = fileName.toLowerCase();
  if (lower.endsWith(".csv")) return "csv";
  if (lower.endsWith(".ofx")) return "ofx";
  return null;
}
