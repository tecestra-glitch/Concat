/**
 * Cookie de sessão do Fronteira FX: token assinado com HMAC-SHA256 (`FX_SESSION_SECRET`).
 *
 * Forma do token: `base64url(JSON {"v":1,"exp":<segundos epoch>}) . base64url(HMAC)`.
 * A expiração fica dentro do valor assinado: mexer no `exp` invalida a assinatura. Sem estado no servidor,
 * então sair = apagar o cookie; trocar `FX_SESSION_SECRET` derruba todas as sessões.
 */
import { createHmac, timingSafeEqual } from "node:crypto";

export const SESSION_COOKIE = "fx_sessao";
/** "Lembrar por 30 dias" (padrão): cookie persistente e token válido por 30 dias. */
export const REMEMBER_TTL_S = 30 * 24 * 60 * 60;
/** Sem "lembrar": cookie de sessão do navegador e token de 12 h. */
export const SHORT_TTL_S = 12 * 60 * 60;

const MAX_TOKEN_LENGTH = 512;

function sign(body: string, secret: string): Buffer {
  return createHmac("sha256", secret).update(body).digest();
}

/** Emite um token que expira em `ttlS` segundos a partir de `nowS`. */
export function signSession(secret: string, nowS: number, ttlS: number): string {
  const body = Buffer.from(JSON.stringify({ v: 1, exp: nowS + ttlS })).toString("base64url");
  return `${body}.${sign(body, secret).toString("base64url")}`;
}

/** `true` só com assinatura íntegra, formato v1 e expiração futura (e não além de 30 dias). */
export function verifySession(token: string | null | undefined, secret: string, nowS: number): boolean {
  if (!token || token.length > MAX_TOKEN_LENGTH || !secret) return false;
  const dot = token.indexOf(".");
  if (dot <= 0 || dot !== token.lastIndexOf(".")) return false;
  const body = token.slice(0, dot);
  const given = Buffer.from(token.slice(dot + 1), "base64url");
  const expected = sign(body, secret);
  if (given.length !== expected.length || !timingSafeEqual(given, expected)) return false;
  let payload: unknown;
  try {
    payload = JSON.parse(Buffer.from(body, "base64url").toString("utf8"));
  } catch {
    return false;
  }
  if (!payload || typeof payload !== "object") return false;
  const { v, exp } = payload as { v?: unknown; exp?: unknown };
  if (v !== 1 || typeof exp !== "number" || !Number.isFinite(exp)) return false;
  return exp > nowS && exp - nowS <= REMEMBER_TTL_S;
}

/** Valor de um cookie num cabeçalho `Cookie:` (ou `null`). */
export function cookieValue(header: string | null | undefined, name: string): string | null {
  if (!header) return null;
  for (const part of header.split(";")) {
    const eq = part.indexOf("=");
    if (eq < 0) continue;
    if (part.slice(0, eq).trim() === name) return part.slice(eq + 1).trim();
  }
  return null;
}
