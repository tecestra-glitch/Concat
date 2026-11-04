import { describe, expect, it } from "vitest";
import { expectedPresentation } from "./plan-helpers";

describe("saída do plano: estimativa não aparece como valor exato", () => {
  it("plano com custo pendente: rótulo de estimativa e prefixo ≈", () => {
    const p = expectedPresentation("1501.53", "USD", "incomplete");
    expect(p.label).toBe("Saída estimada (não confirmada)");
    expect(p.text.startsWith("≈ ")).toBe(true);
    expect(p.text).toContain("1.501,53");
  });

  it("plano confirmado: rótulo normal e sem ≈", () => {
    const p = expectedPresentation("1501.53", "USD", "quoted");
    expect(p.label).toBe("Saída esperada");
    expect(p.text.startsWith("≈")).toBe(false);
    expect(p.text).toContain("1.501,53");
  });
});
