import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { config, proxy } from "@/proxy";
import { basicAuthMatches, basicAuthSetting } from "@/lib/server/frontend-auth";

const basic = (cred: string) => `Basic ${btoa(cred)}`;
afterEach(() => vi.unstubAllEnvs());

describe("FX_BASIC_AUTH gate (SEC-02)", () => {
  it("is off when unset or malformed: every page passes through", () => {
    for (const value of ["", "semdoispontos", ":senha", "usuario:"]) {
      vi.stubEnv("FX_BASIC_AUTH", value);
      expect(basicAuthSetting()).toBeNull();
      expect(proxy(new NextRequest("http://localhost:3000/contas")).status).toBe(200);
    }
  });

  it("asks the browser for credentials on pages and on /api/fx, and lets the right ones through", () => {
    vi.stubEnv("FX_BASIC_AUTH", "eu:senha:com:dois-pontos");
    for (const url of ["http://localhost:3000/", "http://localhost:3000/api/fx/v1/sources"]) {
      const anon = proxy(new NextRequest(url));
      expect(anon.status).toBe(401);
      expect(anon.headers.get("www-authenticate")).toMatch(/^Basic realm=/);
      expect(proxy(new NextRequest(url, { headers: { authorization: basic("eu:errada") } })).status).toBe(401);
      expect(proxy(new NextRequest(url, { headers: { authorization: basic("eu:senha:com:dois-pontos") } })).status).toBe(200);
    }
  });

  it("compares credentials exactly (no prefix match, case-insensitive scheme)", () => {
    expect(basicAuthMatches(basic("eu:senha"), "eu:senha")).toBe(true);
    expect(basicAuthMatches(`basic ${btoa("eu:senha")}`, "eu:senha")).toBe(true);
    expect(basicAuthMatches(basic("eu:senh"), "eu:senha")).toBe(false);
    expect(basicAuthMatches(basic("eu:senhaa"), "eu:senha")).toBe(false);
    expect(basicAuthMatches("Bearer eu:senha", "eu:senha")).toBe(false);
    expect(basicAuthMatches("Basic !!!", "eu:senha")).toBe(false);
    expect(basicAuthMatches(null, "eu:senha")).toBe(false);
  });

  it("does not run on static assets", () => {
    const [matcher] = config.matcher;
    expect(matcher).toContain("_next/static");
  });
});
