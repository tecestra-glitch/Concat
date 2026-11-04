/**
 * Configuração do login próprio do Fronteira FX. Só servidor: lê variáveis sem `NEXT_PUBLIC_`.
 *
 * - `FX_SITE_PASSWORD_HASH` (ver `site-password.ts`) e `FX_SESSION_SECRET` (≥ 32 caracteres) habilitam o login.
 * - Nenhuma das duas: login desligado (vale `FX_BASIC_AUTH`, se houver, e depois o acesso livre).
 * - Só uma das duas, ou formato inválido: configuração quebrada. O proxy fecha tudo (503) a não ser que
 *   `FX_BASIC_AUTH` esteja definido como alternativa; nunca abre o site por engano.
 */
import { isWellFormedPasswordHash } from "./site-password";

export type LoginConfig =
  | { kind: "disabled" }
  | { kind: "enabled"; passwordHash: string; secret: string }
  | { kind: "misconfigured"; reason: string };

export const MIN_SECRET_LENGTH = 32;

export function loginConfig(env: Partial<Record<string, string | undefined>> = process.env): LoginConfig {
  const hash = (env.FX_SITE_PASSWORD_HASH ?? "").trim();
  const secret = (env.FX_SESSION_SECRET ?? "").trim();
  if (!hash && !secret) return { kind: "disabled" };
  if (!hash) return { kind: "misconfigured", reason: "FX_SITE_PASSWORD_HASH vazio" };
  if (!secret) return { kind: "misconfigured", reason: "FX_SESSION_SECRET vazio" };
  if (secret.length < MIN_SECRET_LENGTH) {
    return { kind: "misconfigured", reason: `FX_SESSION_SECRET com menos de ${MIN_SECRET_LENGTH} caracteres` };
  }
  if (!isWellFormedPasswordHash(hash)) return { kind: "misconfigured", reason: "FX_SITE_PASSWORD_HASH com formato inválido" };
  return { kind: "enabled", passwordHash: hash, secret };
}

/**
 * Caminho interno seguro para redirecionar depois do login. Aceita só `/caminho` com origem local:
 * recusa `//host`, `/\host`, esquemas, quebras de linha e o próprio `/entrar`. Qualquer outra coisa vira `/`.
 */
export function safeNextPath(value: string | null | undefined): string {
  if (typeof value !== "string" || value.length === 0 || value.length > 2048) return "/";
  if (!value.startsWith("/") || value.startsWith("//") || value.startsWith("/\\")) return "/";
  if (/[\u0000-\u001f\u007f\\]/.test(value)) return "/";
  let target: URL;
  try {
    target = new URL(value, "http://fronteira.local");
  } catch {
    return "/";
  }
  if (target.origin !== "http://fronteira.local") return "/";
  const path = `${target.pathname}${target.search}`;
  if (target.pathname === "/entrar" || target.pathname === "/entrar/") return "/";
  return path;
}
