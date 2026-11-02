import { describe, expect, it } from "vitest";
import { formatMoney, formatPercent, formatRate, significantFractionDigits } from "@/lib/format";

describe("formatMoney (pt-BR)", () => {
  it("formats BRL with 2 decimals", () => {
    expect(formatMoney("5000", "BRL")).toBe("R$ 5.000,00");
  });
  it("formats PYG without decimals", () => {
    expect(formatMoney("5401871", "PYG")).toBe("₲ 5.401.871");
  });
  it("never rounds a micro-gain to zero", () => {
    const s = formatMoney("0.0037", "BRL", { sign: true });
    expect(s).not.toMatch(/R\$ 0,00$/);
    expect(s).toBe("+R$ 0,0037");
  });
  it("keeps negative sign", () => {
    expect(formatMoney(-12.5, "USD")).toBe("−US$ 12,50");
  });
});

describe("formatPercent", () => {
  it("shows micro ROI", () => {
    expect(formatPercent("0.0000074", { sign: true })).toBe("+0,00074 %");
  });
  it("shows ordinary ROI", () => {
    expect(formatPercent("0.0084")).toBe("0,84 %");
  });
});

describe("formatRate", () => {
  it("PYG integer rates have no decimals", () => {
    expect(formatRate("7350", "PYG")).toBe("7.350");
  });
  it("PYG rates with decimals are rounded to the unit for display", () => {
    expect(formatRate("7335.5", "PYG")).toBe("7.336");
    expect(formatRate("5944.76", "PYG")).toBe("5.945");
    expect(formatRate("1081.5018", "PYG")).toBe("1.082");
  });
  it("BRL rates use 4 decimals", () => {
    expect(formatRate("5.4187", "BRL")).toBe("5,4187");
  });
});

describe("significantFractionDigits", () => {
  it("widens until visible", () => {
    expect(significantFractionDigits(0.004, 2)).toBe(4); // two significant digits: 0,0040
    expect(significantFractionDigits(0.5, 2)).toBe(2);
  });
});
