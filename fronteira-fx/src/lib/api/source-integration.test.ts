import { describe, expect, it } from "vitest";
import { INTEGRATION_LABEL, integrationLabel } from "./source-integration";

describe("integrationLabel (selo de integração da fonte)", () => {
  it("rotula os quatro valores do contrato", () => {
    expect(integrationLabel("api_oficial")).toBe("API oficial");
    expect(integrationLabel("endpoint_interno")).toBe("Endpoint interno");
    expect(integrationLabel("html")).toBe("HTML");
    expect(integrationLabel("navegador")).toBe("Navegador");
  });

  it("valor desconhecido volta como veio, sem quebrar a tela", () => {
    expect(integrationLabel("manual")).toBe("manual");
  });

  it("cobre todos os valores com rótulo não vazio", () => {
    for (const label of Object.values(INTEGRATION_LABEL)) expect(label.length).toBeGreaterThan(0);
  });
});
