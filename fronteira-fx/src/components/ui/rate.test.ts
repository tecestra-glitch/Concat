import { describe, expect, it } from "vitest";
import { formatRateFixed, rateDecimals } from "./rate";

describe("rateDecimals (DS13: casas fixas por grupo)", () => {
  it("casa de câmbio cotando em PYG: 0 casas", () => expect(rateDecimals("PYG")).toBe(0));
  it("referência em PYG (BCP): 2 casas", () => expect(rateDecimals("PYG", { reference: true })).toBe(2));
  it("BRL e USD: 4 casas", () => {
    expect(rateDecimals("BRL")).toBe(4);
    expect(rateDecimals("USD")).toBe(4);
  });
});

describe("formatRateFixed", () => {
  it("PYG de casa com 0 casas e separador pt-BR", () => expect(formatRateFixed("5905", "PYG")).toBe("5.905"));
  it("arredonda a fração de casa em PYG", () => expect(formatRateFixed("5905.4", "PYG")).toBe("5.905"));
  it("referência em PYG mantém 2 casas", () => expect(formatRateFixed("5944.76", "PYG", { reference: true })).toBe("5.944,76"));
  it("BRL com 4 casas", () => expect(formatRateFixed("5.431", "BRL")).toBe("5,4310"));
  it("decimals explícito vence o grupo", () => expect(formatRateFixed("5.431", "BRL", { decimals: 2 })).toBe("5,43"));
  it("null e lixo viram travessão", () => {
    expect(formatRateFixed(null, "PYG")).toBe("—");
    expect(formatRateFixed(undefined, "USD")).toBe("—");
    expect(formatRateFixed("abc", "PYG")).toBe("—");
  });
});
