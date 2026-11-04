import { API_TOKEN_PATTERN, STATEMENT_EXTENSIONS, STATEMENT_MAX_BYTES } from "@/lib/api/connections";

export interface ApiKeyForm {
  apiKey: string;
  apiSecret: string;
  /** Confirmação do usuário: a chave foi criada só com leitura (operar e sacar desmarcados). */
  readOnlyConfirmed: boolean;
}

export const EMPTY_API_KEY_FORM: ApiKeyForm = { apiKey: "", apiSecret: "", readOnlyConfirmed: false };

export interface ApiKeyFormErrors {
  apiKey?: string;
  apiSecret?: string;
  readOnlyConfirmed?: string;
}

const TOKEN_MIN = 16;
const TOKEN_MAX = 256;

function checkToken(raw: string, label: string): string | undefined {
  const v = raw.trim();
  if (!v) return `Informe ${label}.`;
  if (v.length < TOKEN_MIN) return `${label[0].toUpperCase()}${label.slice(1)} curto demais: confira se copiou tudo.`;
  if (v.length > TOKEN_MAX) return `${label[0].toUpperCase()}${label.slice(1)} longo demais.`;
  if (/\s/.test(v) || !API_TOKEN_PATTERN.test(v)) return `${label[0].toUpperCase()}${label.slice(1)} tem caracteres que não são de chave. Copie de novo, sem espaços.`;
  return undefined;
}

/** Erros do formulário de chave de API, por campo. Vazio = pode validar com o servidor. */
export function validateApiKeyForm(f: ApiKeyForm): ApiKeyFormErrors {
  const errors: ApiKeyFormErrors = {};
  const key = checkToken(f.apiKey, "a chave de API");
  if (key) errors.apiKey = key;
  const secret = checkToken(f.apiSecret, "o segredo da API");
  if (secret) errors.apiSecret = secret;
  if (!f.readOnlyConfirmed) errors.readOnlyConfirmed = "Confirme que criou a chave só com leitura, sem operar e sem sacar.";
  return errors;
}

export function hasApiKeyErrors(errors: ApiKeyFormErrors): boolean {
  return Object.values(errors).some(Boolean);
}

/** Erro do arquivo de extrato (extensão e tamanho) ou `null` quando pode enviar. Conteúdo fica para o servidor. */
export function statementFileError(file: { name: string; size: number } | null): string | null {
  if (!file) return "Escolha um arquivo de extrato.";
  const lower = file.name.toLowerCase();
  if (!STATEMENT_EXTENSIONS.some((ext) => lower.endsWith(ext))) return "Use um arquivo .csv ou .ofx.";
  if (file.size <= 0) return "O arquivo está vazio.";
  if (file.size > STATEMENT_MAX_BYTES) return "Arquivo grande demais: o limite é 512 KB.";
  return null;
}
