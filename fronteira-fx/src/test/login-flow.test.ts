import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { proxy } from "@/proxy";
import { attemptLogin, signOut } from "@/lib/server/login";
import { LOGIN_MAX_FAILURES_PER_IP, LOGIN_WINDOW_MS, clearLoginFailures, loginBlocked, recordLoginFailure, resetLoginLimiter } from "@/lib/server/login-limiter";
import { REMEMBER_TTL_S, SESSION_COOKIE, signSession, verifySession } from "@/lib/server/session-token";
import { hashPassword } from "@/lib/server/site-password";
import { frontendGate } from "@/lib/server/frontend-auth";

const SECRET = "segredo-de-teste-com-mais-de-trinta-e-dois-caracteres";
const PASSWORD = "senha-do-dono-de-teste";
const ORIGIN = "http://localhost:3000";
const noSleep = async () => {};

let HASH = "";
beforeEach(async () => {
  HASH = await hashPassword(PASSWORD, { N: 2 ** 10, r: 8, p: 1 });
  vi.stubEnv("FX_SITE_PASSWORD_HASH", HASH);
  vi.stubEnv("FX_SESSION_SECRET", SECRET);
  vi.stubEnv("FX_BASIC_AUTH", "");
  vi.stubEnv("FX_FRONTEND_PROTECTED", "");
  resetLoginLimiter();
});
afterEach(() => {
  vi.unstubAllEnvs();
  vi.useRealTimers();
  resetLoginLimiter();
});

function loginRequest(fields: Record<string, string>, headers: Record<string, string> = {}): Request {
  const body = new URLSearchParams(fields);
  return new Request(`${ORIGIN}/api/sessao/entrar`, {
    method: "POST",
    body,
    headers: { origin: ORIGIN, host: "localhost:3000", "x-forwarded-for": "203.0.113.7", ...headers },
  });
}

function cookieFrom(res: Response): string {
  const raw = res.headers.get("set-cookie") ?? "";
  return raw;
}

describe("POST /api/sessao/entrar", () => {
  it("senha certa: 303 para o destino e cookie httpOnly, Secure, SameSite=Lax de 30 dias", async () => {
    const res = await attemptLogin(loginRequest({ senha: PASSWORD, lembrar: "on", para: "/contas" }), { sleep: noSleep });
    expect(res.status).toBe(303);
    expect(res.headers.get("location")).toBe("/contas");
    const cookie = cookieFrom(res);
    expect(cookie).toMatch(new RegExp(`^${SESSION_COOKIE}=`));
    expect(cookie).toContain("HttpOnly");
    expect(cookie).toContain("Secure");
    expect(cookie).toContain("SameSite=Lax");
    expect(cookie).toContain("Path=/");
    expect(cookie).toContain(`Max-Age=${REMEMBER_TTL_S}`);
    const token = cookie.slice(SESSION_COOKIE.length + 1).split(";")[0];
    expect(verifySession(token, SECRET, Math.floor(Date.now() / 1000))).toBe(true);
  });

  it("sem 'lembrar': cookie de sessão do navegador (sem Max-Age) e token curto", async () => {
    const res = await attemptLogin(loginRequest({ senha: PASSWORD }), { sleep: noSleep });
    const cookie = cookieFrom(res);
    expect(cookie).not.toContain("Max-Age");
    expect(res.headers.get("location")).toBe("/");
  });

  it("senha errada: 303 de volta a /entrar com erro genérico, sem cookie", async () => {
    const res = await attemptLogin(loginRequest({ senha: "errada", para: "/contas" }), { sleep: noSleep });
    expect(res.status).toBe(303);
    expect(res.headers.get("location")).toBe("/entrar?erro=erro&para=%2Fcontas");
    expect(res.headers.get("set-cookie")).toBeNull();
  });

  it("destino externo vindo do formulário é trocado por /", async () => {
    const res = await attemptLogin(loginRequest({ senha: PASSWORD, para: "//evil.example" }), { sleep: noSleep });
    expect(res.headers.get("location")).toBe("/");
  });

  it("aplica o atraso fixo em toda tentativa, certa ou errada", async () => {
    const sleep = vi.fn<(ms: number) => Promise<void>>(noSleep);
    await attemptLogin(loginRequest({ senha: PASSWORD }), { sleep });
    await attemptLogin(loginRequest({ senha: "x" }), { sleep });
    expect(sleep).toHaveBeenCalledTimes(2);
    expect(sleep.mock.calls.every((args) => args[0] === 800)).toBe(true);
  });

  it("bloqueia depois de 5 falhas do mesmo IP, mesmo com a senha certa, e libera após a janela", async () => {
    for (let i = 0; i < LOGIN_MAX_FAILURES_PER_IP; i++) {
      await attemptLogin(loginRequest({ senha: "errada" }), { sleep: noSleep });
    }
    const blocked = await attemptLogin(loginRequest({ senha: PASSWORD }), { sleep: noSleep });
    expect(blocked.headers.get("location")).toBe("/entrar?erro=limite&para=%2F");
    expect(blocked.headers.get("set-cookie")).toBeNull();
    // A janela começa na primeira falha (logo depois de `start`): checa antes e depois dela.
    expect(loginBlocked("203.0.113.7", Date.now() + 1000)).toBe(true);
    expect(loginBlocked("203.0.113.7", Date.now() + LOGIN_WINDOW_MS + 1000)).toBe(false);
  });

  it("IP diferente não herda o bloqueio, mas o teto global vale para todos", async () => {
    for (let i = 0; i < LOGIN_MAX_FAILURES_PER_IP; i++) {
      await attemptLogin(loginRequest({ senha: "errada" }), { sleep: noSleep });
    }
    const other = await attemptLogin(loginRequest({ senha: PASSWORD }, { "x-forwarded-for": "198.51.100.9" }), { sleep: noSleep });
    expect(other.status).toBe(303);
    expect(other.headers.get("set-cookie")).not.toBeNull();
  });

  it("teto global de falhas bloqueia outros IPs (cobre IP forjado em x-forwarded-for)", () => {
    const now = Date.now();
    for (let i = 0; i < 30; i++) recordLoginFailure(`10.0.0.${i}`, now);
    expect(loginBlocked("10.9.9.9", now)).toBe(true);
    clearLoginFailures("10.0.0.1");
    resetLoginLimiter();
  });

  it("recusa origem diferente ou ausente com 403 (CSRF)", async () => {
    const cross = await attemptLogin(loginRequest({ senha: PASSWORD }, { origin: "https://evil.example" }), { sleep: noSleep });
    expect(cross.status).toBe(403);
    const none = new Request(`${ORIGIN}/api/sessao/entrar`, { method: "POST", body: new URLSearchParams({ senha: PASSWORD }), headers: { host: "localhost:3000" } });
    expect((await attemptLogin(none, { sleep: noSleep })).status).toBe(403);
  });

  it("sem login configurado, não cria sessão: volta para a raiz", async () => {
    vi.stubEnv("FX_SITE_PASSWORD_HASH", "");
    vi.stubEnv("FX_SESSION_SECRET", "");
    const res = await attemptLogin(loginRequest({ senha: PASSWORD }), { sleep: noSleep });
    expect(res.headers.get("location")).toBe("/");
    expect(res.headers.get("set-cookie")).toBeNull();
  });
});

describe("POST /sair", () => {
  it("apaga o cookie e volta ao início; origem cruzada leva 403", async () => {
    const ok = signOut(new Request(`${ORIGIN}/sair`, { method: "POST", headers: { origin: ORIGIN, host: "localhost:3000" } }));
    expect(ok.status).toBe(303);
    const cookie = ok.headers.get("set-cookie") ?? "";
    expect(cookie).toContain(`${SESSION_COOKIE}=;`);
    expect(cookie).toContain("Max-Age=0");
    expect(cookie).toContain("HttpOnly");
    const cross = signOut(new Request(`${ORIGIN}/sair`, { method: "POST", headers: { origin: "https://evil.example", host: "localhost:3000" } }));
    expect(cross.status).toBe(403);
  });
});

describe("proxy com login próprio", () => {
  const session = () => signSession(SECRET, Math.floor(Date.now() / 1000), REMEMBER_TTL_S);
  const withCookie = (url: string, value: string) => new NextRequest(url, { headers: { cookie: `${SESSION_COOKIE}=${value}` } });

  it("página sem sessão vai para /entrar com o caminho pedido (incluindo a query)", () => {
    const res = proxy(new NextRequest("http://localhost:3000/contas?aba=x"));
    expect(res.status).toBe(307);
    expect(res.headers.get("location")).toBe("http://localhost:3000/entrar?para=%2Fcontas%3Faba%3Dx");
  });

  it("raiz sem sessão vai para /entrar sem parâmetro", () => {
    const res = proxy(new NextRequest("http://localhost:3000/"));
    expect(res.headers.get("location")).toBe("http://localhost:3000/entrar");
  });

  it("/api/fx sem sessão responde 401 em JSON, sem redirecionar", () => {
    const res = proxy(new NextRequest("http://localhost:3000/api/fx/v1/sources"));
    expect(res.status).toBe(401);
    expect(res.headers.get("content-type")).toContain("application/json");
  });

  it("com sessão válida passa; cookie adulterado ou de outro segredo não passa", () => {
    expect(proxy(withCookie("http://localhost:3000/contas", session())).status).toBe(200);
    expect(proxy(withCookie("http://localhost:3000/contas", "x.y")).status).toBe(307);
    const other = signSession("outro-segredo-bem-diferente-de-trinta-e-dois", Math.floor(Date.now() / 1000), 60);
    expect(proxy(withCookie("http://localhost:3000/api/fx/v1/sources", other)).status).toBe(401);
  });

  it("rotas públicas de login ficam abertas", () => {
    for (const path of ["/entrar", "/entrar/", "/api/sessao/entrar", "/sair"]) {
      expect(proxy(new NextRequest(`http://localhost:3000${path}`)).status).toBe(200);
    }
  });

  it("configuração quebrada fecha tudo com 503 (sem FX_BASIC_AUTH)", () => {
    vi.stubEnv("FX_SESSION_SECRET", "");
    expect(proxy(new NextRequest("http://localhost:3000/contas")).status).toBe(503);
  });

  it("FX_BASIC_AUTH continua valendo quando o login novo não está configurado", () => {
    vi.stubEnv("FX_SITE_PASSWORD_HASH", "");
    vi.stubEnv("FX_SESSION_SECRET", "");
    vi.stubEnv("FX_BASIC_AUTH", "eu:senha");
    expect(proxy(new NextRequest("http://localhost:3000/contas")).status).toBe(401);
    const basic = `Basic ${btoa("eu:senha")}`;
    expect(proxy(new NextRequest("http://localhost:3000/contas", { headers: { authorization: basic } })).status).toBe(200);
  });

  it("sem nenhum login, o app passa direto", () => {
    vi.stubEnv("FX_SITE_PASSWORD_HASH", "");
    vi.stubEnv("FX_SESSION_SECRET", "");
    expect(proxy(new NextRequest("http://localhost:3000/contas")).status).toBe(200);
  });
});

describe("gate do /api/fx com login próprio", () => {
  it("só libera a chave da API com sessão válida", () => {
    const token = signSession(SECRET, Math.floor(Date.now() / 1000), REMEMBER_TTL_S);
    expect(frontendGate(new Request("http://localhost/api/fx/v1/x", { headers: { cookie: `${SESSION_COOKIE}=${token}` } })).kind).toBe("trusted");
    expect(frontendGate(new Request("http://localhost/api/fx/v1/x")).kind).toBe("unauthenticated");
  });
});
