import { describe, expect, it } from "vitest";
import { NAV } from "@/components/shell/nav";

describe("navegação: Planos", () => {
  it("Planos aparece logo depois de Oportunidades", () => {
    const i = NAV.findIndex((n) => n.href === "/oportunidades");
    expect(NAV[i + 1]).toMatchObject({ href: "/planos", label: "Planos" });
  });
});
