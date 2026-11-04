import { describe, expect, it } from "vitest";
import { NAV, isActive, splitNav } from "./nav";

describe("NAV", () => {
  it("inclui as telas de conhecimento e memória", () => {
    const hrefs = NAV.map((n) => n.href);
    expect(hrefs).toContain("/conhecimento");
    expect(hrefs).toContain("/memoria");
  });

  it("Pregão vem logo depois de Mercados e fica na barra inferior do celular", () => {
    const i = NAV.findIndex((n) => n.href === "/pregao");
    expect(NAV[i - 1]?.href).toBe("/mercados");
    expect(NAV[i]).toMatchObject({ label: "Pregão", short: "Pregão" });
    expect(splitNav(NAV).primary.map((n) => n.href)).toContain("/pregao");
  });
});

describe("Economia e cripto (módulo market)", () => {
  it("tem rota própria, distinta de /mercados (que é a tela das casas), sem casar por prefixo", () => {
    const item = NAV.find((n) => n.href === "/economia");
    expect(item).toMatchObject({ label: "Economia e cripto" });
    expect(isActive("/economia", "/mercados")).toBe(false);
    expect(isActive("/mercados", "/economia")).toBe(false);
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
