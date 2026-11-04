import { describe, expect, it } from "vitest";
import { CitySchema } from "@/lib/api/schemas";
import { HouseCitySchema, HouseSessionSchema } from "@/lib/pregao/schemas";

describe("HouseCitySchema: mesmo conjunto de cidades do contrato da API", () => {
  it("aceita CDE, ASU, PJC e FOZ", () => {
    for (const city of ["CDE", "ASU", "PJC", "FOZ"]) {
      expect(HouseCitySchema.safeParse(city).success).toBe(true);
    }
  });

  it("recusa cidade fora do contrato", () => {
    expect(HouseCitySchema.safeParse("XXX").success).toBe(false);
  });

  it("coincide com CitySchema (sem o null, que o pregão trata à parte)", () => {
    const apiCities = CitySchema.unwrap().options;
    expect([...HouseCitySchema.options].sort()).toEqual([...apiCities].sort());
  });

  it("uma sessão de casa de Foz do Iguaçu valida", () => {
    const parsed = HouseSessionSchema.safeParse({
      source_id: "atlas",
      name: "Atlas Câmbio",
      city: "FOZ",
      tz: "America/Asuncion",
      channel: "physical",
      reference: false,
      status: "open",
      opens_at: "2026-11-04T12:00:00Z",
      closes_at: "2026-11-04T20:00:00Z",
      next_change_at: null,
      data_mode: "real",
    });
    expect(parsed.success).toBe(true);
  });
});
