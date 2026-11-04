/**
 * Lógica das rotas de entrar (POST /api/sessao/entrar) e sair (POST /sair). Fica fora dos arquivos de rota
 * porque o Next só aceita métodos HTTP e configuração de segmento nesses arquivos.
 *
 * CSRF: as duas rotas aceitam só POST com `Origin` igual ao host. O cookie é SameSite=Lax, o que já barra
 * POST entre sites; a checagem de Origin é a segunda camada.
 */
import { SESSION_COOKIE, REMEMBER_TTL_S, SHORT_TTL_S, signSession, verifySession } from "./session-token";
import { loginConfig, safeNextPath } from "./site-login";
import { verifyPassword } from "./site-password";
import {
  LOGIN_DELAY_MS,
  clearLoginFailures,
  clientKey,
  loginBlocked,
  recordLoginFailure,
} from "./login-limiter";

export const MAX_PASSWORD_LENGTH = 1024;

/** O cabeçalho `Origin` existe e tem o mesmo host que o pedido? */
export function isSameOrigin(req: Request): boolean {
  const origin = req.headers.get("origin");
  if (!origin || origin === "null") return false;
  const host = (req.headers.get("x-forwarded-host") ?? req.headers.get("host") ?? new URL(req.url).host).split(",")[0].trim();
  try {
    return new URL(origin).host === host;
  } catch {
    return false;
  }
}

/** Cabeçalho `Set-Cookie` com o token. Sem `maxAgeS` vira cookie de sessão do navegador. */
export function sessionSetCookie(token: string, maxAgeS: number | null): string {
  const attributes = ["Path=/", "HttpOnly", "Secure", "SameSite=Lax"];
  if (maxAgeS !== null) attributes.push(`Max-Age=${maxAgeS}`);
  return [`${SESSION_COOKIE}=${token}`, ...attributes].join("; ");
}

/** Cabeçalho `Set-Cookie` que apaga o cookie. */
export function sessionClearCookie(): string {
  return `${SESSION_COOKIE}=; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=0`;
}

function redirect(location: string, setCookie?: string): Response {
  const headers = new Headers({ location, "cache-control": "no-store" });
  if (setCookie) headers.append("set-cookie", setCookie);
  return new Response(null, { status: 303, headers });
}

function loginPage(params: Record<string, string>): string {
  const query = new URLSearchParams(params).toString();
  return query ? `/entrar?${query}` : "/entrar";
}

const MSG_ERRO = "erro";
const MSG_LIMITE = "limite";

export type LoginDeps = { sleep?: (ms: number) => Promise<void>; now?: () => number };
const realSleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

/** POST do formulário de entrada. Sempre responde 303: sucesso leva ao destino com cookie; falha volta ao /entrar. */
export async function attemptLogin(req: Request, deps: LoginDeps = {}): Promise<Response> {
  const sleep = deps.sleep ?? realSleep;
  const nowMs = deps.now ?? Date.now;
  if (!isSameOrigin(req)) return new Response("Origem recusada.", { status: 403, headers: { "cache-control": "no-store" } });

  const config = loginConfig();
  if (config.kind !== "enabled") return redirect("/");

  const form = await req.formData().catch(() => null);
  const password = typeof form?.get("senha") === "string" ? (form!.get("senha") as string) : "";
  const remember = form?.get("lembrar") === "on";
  const para = safeNextPath(typeof form?.get("para") === "string" ? (form!.get("para") as string) : null);
  const key = clientKey(req.headers);

  if (loginBlocked(key, nowMs())) {
    await sleep(LOGIN_DELAY_MS);
    return redirect(loginPage({ erro: MSG_LIMITE, para }));
  }

  // Atraso fixo antes de conferir: o tempo de resposta não separa senha certa de errada.
  await sleep(LOGIN_DELAY_MS);
  const ok = password.length > 0 && password.length <= MAX_PASSWORD_LENGTH && (await verifyPassword(password, config.passwordHash));
  if (!ok) {
    recordLoginFailure(key, nowMs());
    return redirect(loginPage({ erro: MSG_ERRO, para }));
  }

  clearLoginFailures(key);
  const nowS = Math.floor(nowMs() / 1000);
  const ttl = remember ? REMEMBER_TTL_S : SHORT_TTL_S;
  const token = signSession(config.secret, nowS, ttl);
  return redirect(para, sessionSetCookie(token, remember ? REMEMBER_TTL_S : null));
}

/** POST de sair: apaga o cookie e volta ao início (o proxy manda para /entrar se a sessão já não valer). */
export function signOut(req: Request): Response {
  if (!isSameOrigin(req)) return new Response("Origem recusada.", { status: 403, headers: { "cache-control": "no-store" } });
  return redirect("/", sessionClearCookie());
}

/** Token de sessão vale agora? (relógio lido aqui, fora dos componentes, para a página /entrar). */
export function sessionValidNow(token: string | null | undefined, secret: string): boolean {
  return verifySession(token, secret, Math.floor(Date.now() / 1000));
}

/** A sessão deste pedido vale? Usado pelo proxy, pelo gate do /api/fx e pela página /entrar. */
export function requestHasValidSession(cookieHeader: string | null, secret: string, nowS: number = Math.floor(Date.now() / 1000)): boolean {
  const match = cookieHeader?.split(";").map((p) => p.trim()).find((p) => p.startsWith(`${SESSION_COOKIE}=`));
  const token = match ? match.slice(SESSION_COOKIE.length + 1) : null;
  return verifySession(token, secret, nowS);
}
