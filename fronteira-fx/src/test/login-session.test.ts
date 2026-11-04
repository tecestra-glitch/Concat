import { createHmac } from "node:crypto";
import { describe, expect, it } from "vitest";
import { REMEMBER_TTL_S, SHORT_TTL_S, cookieValue, deriveSessionKey, signSession, verifySession } from "@/lib/server/session-token";
import { loginConfig, safeNextPath } from "@/lib/server/site-login";
import { hashPassword } from "@/lib/server/site-password";
import { requestHasValidSession } from "@/lib/server/login";

const SECRET = "segredo-de-teste-com-mais-de-trinta-e-dois-caracteres";
const NOW = 1_800_000_000;

describe("cookie de sessão assinado", () => {
  it("aceita token íntegro dentro da validade", () => {
    const token = signSession(SECRET, NOW, REMEMBER_TTL_S);
    expect(verifySession(token, SECRET, NOW)).toBe(true);
    expect(verifySession(token, SECRET, NOW + REMEMBER_TTL_S - 1)).toBe(true);
  });

  it("recusa token expirado (inclusive no instante exato da expiração)", () => {
    const token = signSession(SECRET, NOW, SHORT_TTL_S);
    expect(verifySession(token, SECRET, NOW + SHORT_TTL_S - 1)).toBe(true);
    expect(verifySession(token, SECRET, NOW + SHORT_TTL_S)).toBe(false);
    expect(verifySession(token, SECRET, NOW + REMEMBER_TTL_S)).toBe(false);
  });

  it("recusa token assinado com outro segredo", () => {
    const token = signSession("outro-segredo-bem-diferente-de-trinta-e-dois", NOW, REMEMBER_TTL_S);
    expect(verifySession(token, SECRET, NOW)).toBe(false);
  });

  it("recusa payload adulterado (estender a expiração muda o corpo assinado)", () => {
    const token = signSession(SECRET, NOW, SHORT_TTL_S);
    const [, sig] = token.split(".");
    const forged = Buffer.from(JSON.stringify({ v: 1, exp: NOW + REMEMBER_TTL_S - 10 })).toString("base64url");
    expect(verifySession(`${forged}.${sig}`, SECRET, NOW)).toBe(false);
  });

  it("recusa assinatura adulterada, truncada ou com formato errado", () => {
    const token = signSession(SECRET, NOW, REMEMBER_TTL_S);
    const [body, sig] = token.split(".");
    const flipped = sig.endsWith("A") ? `${sig.slice(0, -1)}B` : `${sig.slice(0, -1)}A`;
    expect(verifySession(`${body}.${flipped}`, SECRET, NOW)).toBe(false);
    expect(verifySession(`${body}.${sig.slice(0, 10)}`, SECRET, NOW)).toBe(false);
    expect(verifySession(`${body}.${sig}.extra`, SECRET, NOW)).toBe(false);
    expect(verifySession(body, SECRET, NOW)).toBe(false);
    expect(verifySession(`.${sig}`, SECRET, NOW)).toBe(false);
    expect(verifySession("", SECRET, NOW)).toBe(false);
    expect(verifySession(undefined, SECRET, NOW)).toBe(false);
    expect(verifySession("x".repeat(600), SECRET, NOW)).toBe(false);
  });

  it("recusa payload sem versão 1 ou com expiração absurda, mesmo bem assinado", () => {
    const signed = (payload: object) => {
      const body = Buffer.from(JSON.stringify(payload)).toString("base64url");
      return `${body}.${createHmac("sha256", SECRET).update(body).digest("base64url")}`;
    };
    expect(verifySession(signed({ v: 2, exp: NOW + 60 }), SECRET, NOW)).toBe(false);
    expect(verifySession(signed({ exp: NOW + 60 }), SECRET, NOW)).toBe(false);
    expect(verifySession(signed({ v: 1, exp: "amanhã" }), SECRET, NOW)).toBe(false);
    expect(verifySession(signed({ v: 1, exp: NOW + REMEMBER_TTL_S * 10 }), SECRET, NOW)).toBe(false);
    expect(verifySession(signed(["não", "é", "objeto"]), SECRET, NOW)).toBe(false);
  });

  it("lê o cookie certo do cabeçalho Cookie e ignora nomes parecidos", () => {
    expect(cookieValue("a=1; fx_sessao=tok.en; b=2", "fx_sessao")).toBe("tok.en");
    expect(cookieValue("xfx_sessao=nope; fx_sessao_old=nope", "fx_sessao")).toBeNull();
    expect(cookieValue(null, "fx_sessao")).toBeNull();
    expect(requestHasValidSession(`fx_sessao=${signSession(SECRET, NOW, SHORT_TTL_S)}`, SECRET, NOW)).toBe(true);
    expect(requestHasValidSession("fx_sessao=lixo", SECRET, NOW)).toBe(false);
  });
});

describe("configuração do login (loginConfig)", () => {
  it("fica desligado sem as duas variáveis", () => {
    expect(loginConfig({})).toEqual({ kind: "disabled" });
    expect(loginConfig({ FX_SITE_PASSWORD_HASH: "  ", FX_SESSION_SECRET: "" })).toEqual({ kind: "disabled" });
  });

  it("habilita com hash bem formado e segredo de 32+ caracteres", async () => {
    const hash = await hashPassword("x", { N: 2 ** 10, r: 8, p: 1 });
    expect(loginConfig({ FX_SITE_PASSWORD_HASH: hash, FX_SESSION_SECRET: SECRET })).toEqual({
      kind: "enabled",
      passwordHash: hash,
      sessionKey: deriveSessionKey(SECRET, hash),
    });
  });

  it("a chave de sessão depende do hash: outra senha, outra chave (e o segredo cru nunca é usado para assinar)", async () => {
    const hash = await hashPassword("x", { N: 2 ** 10, r: 8, p: 1 });
    const other = await hashPassword("y", { N: 2 ** 10, r: 8, p: 1 });
    const a = loginConfig({ FX_SITE_PASSWORD_HASH: hash, FX_SESSION_SECRET: SECRET });
    const b = loginConfig({ FX_SITE_PASSWORD_HASH: other, FX_SESSION_SECRET: SECRET });
    expect(a.kind === "enabled" && b.kind === "enabled" && a.sessionKey !== b.sessionKey).toBe(true);
    expect(a.kind === "enabled" && a.sessionKey !== SECRET).toBe(true);
  });

  it("marca como quebrado quando falta uma das duas, o segredo é curto ou o hash é inválido", async () => {
    const hash = await hashPassword("x", { N: 2 ** 10, r: 8, p: 1 });
    expect(loginConfig({ FX_SITE_PASSWORD_HASH: hash }).kind).toBe("misconfigured");
    expect(loginConfig({ FX_SESSION_SECRET: SECRET }).kind).toBe("misconfigured");
    expect(loginConfig({ FX_SITE_PASSWORD_HASH: hash, FX_SESSION_SECRET: "curto" }).kind).toBe("misconfigured");
    expect(loginConfig({ FX_SITE_PASSWORD_HASH: "senha-em-texto-puro", FX_SESSION_SECRET: SECRET }).kind).toBe("misconfigured");
  });
});

describe("destino depois do login (safeNextPath, sem open redirect)", () => {
  it("aceita caminhos internos, com query", () => {
    expect(safeNextPath("/contas")).toBe("/contas");
    expect(safeNextPath("/planos/abc?aba=cdes")).toBe("/planos/abc?aba=cdes");
    expect(safeNextPath("/")).toBe("/");
  });

  it("recusa origem externa e truques de barra", () => {
    for (const value of ["//evil.example", "/\\evil.example", "https://evil.example", "http:evil", "javascript:alert(1)", "evil.example", "///evil.example"]) {
      expect(safeNextPath(value)).toBe("/");
    }
  });

  it("recusa quebra de linha, controle, o próprio /entrar e valores vazios ou gigantes", () => {
    expect(safeNextPath("/contas\nSet-Cookie: x")).toBe("/");
    expect(safeNextPath("/contas\\x")).toBe("/");
    expect(safeNextPath("/entrar")).toBe("/");
    expect(safeNextPath("/entrar?para=/x")).toBe("/");
    expect(safeNextPath("")).toBe("/");
    expect(safeNextPath(null)).toBe("/");
    expect(safeNextPath(undefined)).toBe("/");
    expect(safeNextPath(`/${"a".repeat(3000)}`)).toBe("/");
  });
});
