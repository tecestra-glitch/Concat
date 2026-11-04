/**
 * Proteção do frontend (SEC-02). Só roda no servidor: lê variáveis sem `NEXT_PUBLIC_`.
 *
 * O proxy `/api/fx` injeta `FX_API_KEY`; quem alcança o frontend herda essa chave. Por isso a chave só sai
 * quando o operador protegeu o frontend:
 * - `FX_BASIC_AUTH="usuario:senha"` → `src/proxy.ts` pede Basic Auth em todas as páginas e o proxy confere
 *   o cabeçalho de novo antes de injetar a chave;
 * - `FX_FRONTEND_PROTECTED=1` → o operador declara que o frontend já é privado por outro meio (loopback do
 *   compose, VPN, Vercel Deployment Protection).
 * Sem nenhum dos dois, leituras seguem sem chave e mutações são recusadas pelo proxy.
 */

import { loginConfig } from "./site-login";
import { requestHasValidSession } from "./login";

export const BASIC_REALM = 'Basic realm="Fronteira FX", charset="UTF-8"';

/** `FX_BASIC_AUTH` quando bem formado (`usuario:senha`, senha não vazia); `null` caso contrário. */
export function basicAuthSetting(): string | null {
  const raw = (process.env.FX_BASIC_AUTH ?? "").trim();
  const sep = raw.indexOf(":");
  return sep > 0 && sep < raw.length - 1 ? raw : null;
}

/** Comparação em tempo constante para o comprimento esperado (não revela onde diverge). */
function sameSecret(given: string, expected: string): boolean {
  let diff = given.length ^ expected.length;
  for (let i = 0; i < expected.length; i++) diff |= (given.charCodeAt(i) || 0) ^ expected.charCodeAt(i);
  return diff === 0;
}

function decodeBase64(value: string): string | null {
  try {
    const bytes = Uint8Array.from(atob(value), (c) => c.charCodeAt(0));
    return new TextDecoder().decode(bytes);
  } catch {
    return null;
  }
}

/** O cabeçalho `Authorization: Basic …` traz exatamente `expected` (`usuario:senha`)? */
export function basicAuthMatches(header: string | null, expected: string): boolean {
  if (!header || !/^basic\s+/i.test(header)) return false;
  const decoded = decodeBase64(header.replace(/^basic\s+/i, "").trim());
  return decoded !== null && sameSecret(decoded, expected);
}

export type FrontendGate = { kind: "trusted" } | { kind: "unprotected" } | { kind: "unauthenticated" };

/**
 * Decide se esta requisição pode levar a chave da API. Ordem: login próprio (`FX_SITE_PASSWORD_HASH` +
 * `FX_SESSION_SECRET`) → `FX_BASIC_AUTH` → `FX_FRONTEND_PROTECTED`. Com o login configurado quebrado e sem
 * Basic Auth, nada passa.
 */
export function frontendGate(req: Request): FrontendGate {
  const login = loginConfig();
  if (login.kind === "enabled") {
    return requestHasValidSession(req.headers.get("cookie"), login.sessionKey) ? { kind: "trusted" } : { kind: "unauthenticated" };
  }
  const basic = basicAuthSetting();
  if (basic) return basicAuthMatches(req.headers.get("authorization"), basic) ? { kind: "trusted" } : { kind: "unauthenticated" };
  if (login.kind === "misconfigured") return { kind: "unauthenticated" };
  return (process.env.FX_FRONTEND_PROTECTED ?? "").trim() === "1" ? { kind: "trusted" } : { kind: "unprotected" };
}
