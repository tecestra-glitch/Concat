/**
 * Contrato de conexões de contas (`/v1/connections`). Tipos zod construídos a partir da especificação da tela de
 * conexões, porque o backend está sendo feito em paralelo. Quando `docs/api-contract.md` ganhar esta seção, ela
 * vira a fonte da verdade e estes schemas são ajustados nos dois lados.
 *
 * Regras que valem para todo o módulo:
 * - o app NUNCA recebe, guarda ou mostra senha de banco. Segredo de API (`api_secret`) só sai do navegador no POST
 *   de validação/criação e nunca volta na resposta;
 * - a resposta traz só `key_hint` (últimos 4 caracteres), nunca a chave completa;
 * - a chave precisa ser só de leitura: uma chave que pode operar ou sacar é recusada aqui e no servidor;
 * - o conteúdo de extratos (CSV/OFX) é dado não confiável: o servidor lê, a tela não interpreta.
 */
import { z } from "zod";

export const ConnectionMethodSchema = z.enum(["open_finance", "api_key_readonly", "statement_import", "manual_balance"]);
export type ConnectionMethod = z.infer<typeof ConnectionMethodSchema>;

export const ConnectionStatusSchema = z.enum(["pending", "active", "error", "revoked"]);
export type ConnectionStatus = z.infer<typeof ConnectionStatusSchema>;

export const ConnectionDataModeSchema = z.enum(["real", "simulation", "demo"]);

export const ConnectionSchema = z.object({
  id: z.string(),
  institution_id: z.string(),
  institution_name: z.string(),
  method: ConnectionMethodSchema,
  status: ConnectionStatusSchema,
  /** Últimos 4 caracteres da chave, nunca a chave. `null` quando o método não tem chave. */
  key_hint: z.string().max(4).nullable(),
  created_at: z.string(),
  last_sync_at: z.string().nullable(),
  data_mode: ConnectionDataModeSchema,
});
export type Connection = z.infer<typeof ConnectionSchema>;

/** `GET /v1/connections`: conexões do modo + se há agregador de Open Finance configurado no servidor. */
export const ConnectionListSchema = z.object({
  aggregator_configured: z.boolean(),
  connections: z.array(ConnectionSchema),
});
export type ConnectionList = z.infer<typeof ConnectionListSchema>;

/** `POST /v1/connections/validate-key`: o servidor consulta as permissões da chave (nada é gravado). */
export const ApiKeyValidationSchema = z.object({
  read: z.boolean(),
  trade: z.boolean(),
  withdraw: z.boolean(),
});
export type ApiKeyValidation = z.infer<typeof ApiKeyValidationSchema>;

/** `POST /v1/connections/open-finance`: devolve o endereço de consentimento do agregador. */
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

/** `POST /v1/connections/statements` (multipart): o servidor lê o arquivo e informa quantas linhas entenderam. */
export const StatementImportResultSchema = z.object({
  connection: ConnectionSchema,
  rows_read: z.number().int().nonnegative(),
  rows_skipped: z.number().int().nonnegative(),
});
export type StatementImportResult = z.infer<typeof StatementImportResultSchema>;

/** Corpo do POST de chave de API (validação e criação usam o mesmo formato). */
export const ApiKeyInputSchema = z.object({
  institution_id: z.string().min(1),
  api_key: z.string().min(16).max(256),
  api_secret: z.string().min(16).max(256),
});
export type ApiKeyInput = z.infer<typeof ApiKeyInputSchema>;

/** Formato aceito de chave e segredo: caracteres de token comuns, sem espaços (copiar e colar costuma trazer espaço). */
export const API_TOKEN_PATTERN = /^[A-Za-z0-9_\-+/=.]+$/;

/**
 * Mensagem de recusa para uma chave que pode operar ou sacar, ou `null` quando a chave é só de leitura. A regra é
 * dupla: a tela recusa antes de salvar e o servidor recusa de novo (defesa em profundidade).
 */
export function apiKeyRefusal(v: ApiKeyValidation): string | null {
  if (v.trade && v.withdraw) return "Esta chave pode operar e sacar. O Fronteira FX recusa chaves assim. Crie outra só com leitura.";
  if (v.trade) return "Esta chave pode operar (negociar). O Fronteira FX recusa chaves assim. Crie outra só com leitura.";
  if (v.withdraw) return "Esta chave pode sacar. O Fronteira FX recusa chaves assim. Crie outra só com leitura.";
  if (!v.read) return "Esta chave não tem permissão de leitura. Crie uma chave com leitura marcada.";
  return null;
}

/** Últimos 4 caracteres da chave; `null` para chave curta demais (menos de 8), que não mostra nenhum pedaço. */
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

/** Caminhos da API (sem a base `/api/fx`). Modo entra pela query, como no resto do cliente. */
export const CONNECTIONS_PATH = "/v1/connections";
export const connectionPath = (id: string): string => `${CONNECTIONS_PATH}/${encodeURIComponent(id)}`;

/** Extensões e tamanho máximo de extrato aceitos pela tela (o servidor valida de novo). */
export const STATEMENT_EXTENSIONS = [".csv", ".ofx"] as const;
export const STATEMENT_MAX_BYTES = 5 * 1024 * 1024;
