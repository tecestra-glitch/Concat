import { describe, expect, it } from "vitest";
import { NAV, isActive, splitNav } from "./nav";

describe("NAV", () => {
  it("inclui as telas de conhecimento e memória", () => {
    const hrefs = NAV.map((n) => n.href);
    expect(hrefs).toContain("/conhecimento");
    expect(hrefs).toContain("/memoria");
  });
});

describe("splitNav (barra inferior + menu Mais)", () => {
  it("4 itens principais e o resto no menu Mais, sem perder rota", () => {
    const { primary, more } = splitNav(NAV);
    expect(primary).toHaveLength(4);
    expect(primary[0].href).toBe("/");
    expect(more.length).toBe(NAV.length - 4);
    expect([...primary, ...more].map((n) => n.href).sort()).toEqual(NAV.map((n) => n.href).sort());
  });
});

describe("isActive", () => {
  it("raiz só casa exatamente", () => {
    expect(isActive("/", "/")).toBe(true);
    expect(isActive("/", "/mercados")).toBe(false);
  });
  it("demais rotas casam por prefixo", () => {
    expect(isActive("/mercados", "/mercados")).toBe(true);
    expect(isActive("/mercados", "/mercados/x")).toBe(true);
    expect(isActive("/memoria", "/mercados")).toBe(false);
  });
});
