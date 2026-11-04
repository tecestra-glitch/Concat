/**
 * Proxy do Next 16 (antigo middleware): porta de entrada do app. Três modos, nesta ordem:
 *
 * 1. Login próprio (`FX_SITE_PASSWORD_HASH` + `FX_SESSION_SECRET`): toda página e todo `/api/fx` exigem o cookie
 *    de sessão assinado. Sem ele, páginas vão para `/entrar?para=<caminho>` e `/api/fx` responde 401. `/entrar`,
 *    `/api/sessao/entrar` e `/sair` ficam públicas (são elas que criam e apagam a sessão).
 * 2. Configuração quebrada (só uma das duas variáveis, ou segredo curto): fecha tudo com 503, a não ser que
 *    `FX_BASIC_AUTH` esteja definido como alternativa.
 * 3. `FX_BASIC_AUTH="usuario:senha"`: Basic Auth do navegador em todo o app (SEC-02). Sem nada disso o app passa
 *    direto, e o proxy `/api/fx` só injeta a chave da API com `FX_FRONTEND_PROTECTED=1`.
 */
import { NextResponse, type NextRequest } from "next/server";
import { BASIC_REALM, basicAuthMatches, basicAuthSetting } from "@/lib/server/frontend-auth";
import { SESSION_COOKIE, verifySession } from "@/lib/server/session-token";
import { loginConfig } from "@/lib/server/site-login";

/** Rotas que precisam ficar abertas para o login acontecer. */
const PUBLIC_PATHS = new Set(["/entrar", "/api/sessao/entrar", "/sair"]);

function noStore(headers: Record<string, string> = {}): Record<string, string> {
  return { "cache-control": "no-store", ...headers };
}

function sessionGate(request: NextRequest, secret: string): NextResponse {
  const { pathname } = request.nextUrl;
  const bare = pathname.length > 1 ? pathname.replace(/\/+$/, "") : pathname;
  if (PUBLIC_PATHS.has(bare)) return NextResponse.next();
  const token = request.cookies.get(SESSION_COOKIE)?.value;
  if (verifySession(token, secret, Math.floor(Date.now() / 1000))) return NextResponse.next();
  if (bare.startsWith("/api/")) {
    return new NextResponse(JSON.stringify({ detail: "Autenticação necessária." }), {
      status: 401,
      headers: noStore({ "content-type": "application/json; charset=utf-8" }),
    });
  }
  const target = new URL("/entrar", request.url);
  const para = `${pathname}${request.nextUrl.search}`;
  if (para !== "/") target.searchParams.set("para", para);
  return NextResponse.redirect(target);
}

export function proxy(request: NextRequest): NextResponse {
  const login = loginConfig();
  if (login.kind === "enabled") return sessionGate(request, login.sessionKey);

  const basic = basicAuthSetting();
  if (login.kind === "misconfigured" && !basic) {
    return new NextResponse(`Login mal configurado no servidor (${login.reason}). Acesso bloqueado.`, {
      status: 503,
      headers: noStore({ "content-type": "text/plain; charset=utf-8" }),
    });
  }
  if (!basic || basicAuthMatches(request.headers.get("authorization"), basic)) return NextResponse.next();
  return new NextResponse("Autenticação necessária.", {
    status: 401,
    headers: { "www-authenticate": BASIC_REALM, "cache-control": "no-store", "content-type": "text/plain; charset=utf-8" },
  });
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
