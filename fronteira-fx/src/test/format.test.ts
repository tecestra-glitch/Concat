import { describe, expect, it } from "vitest";
import { ageSeconds, formatAge, formatMoney, formatPercent, formatRate, parseDecimalPtBR, significantFractionDigits } from "@/lib/format";

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

describe("parseDecimalPtBR", () => {
  it("reads pt-BR thousands and decimal separators into a canonical decimal string", () => {
    expect(parseDecimalPtBR("5.000")).toBe("5000");
    expect(parseDecimalPtBR("5.000,50")).toBe("5000.5");
    expect(parseDecimalPtBR("1.250,5")).toBe("1250.5");
    expect(parseDecimalPtBR("1.000.000")).toBe("1000000");
    expect(parseDecimalPtBR("0,25")).toBe("0.25");
  });
  it("still accepts a plain dot decimal when it cannot be a thousands group", () => {
    expect(parseDecimalPtBR("0.25")).toBe("0.25");
    expect(parseDecimalPtBR("5.4187")).toBe("5.4187");
    expect(parseDecimalPtBR("12.5")).toBe("12.5");
  });
  it("trims, keeps the sign and normalises a leading separator", () => {
    expect(parseDecimalPtBR(" 15 ")).toBe("15");
    expect(parseDecimalPtBR("-1")).toBe("-1");
    expect(parseDecimalPtBR(",5")).toBe("0.5");
    expect(parseDecimalPtBR("1,50")).toBe("1.5");
  });
  it("rejects what is not a number", () => {
    for (const bad of ["", "abc", "1,2,3", ".", "-", "1.00.0", "1,5.2", "1.0000", "12.34.5"]) {
      expect(parseDecimalPtBR(bad), bad).toBeNull();
    }
  });
  it("does not go through a float (keeps every digit)", () => {
    expect(parseDecimalPtBR("12345678901234567890,123456789")).toBe("12345678901234567890.123456789");
  });
});

describe("formatAge / ageSeconds take an explicit clock", () => {
  const now = Date.parse("2026-11-02T12:00:00Z");
  it("formats relative ages against the clock passed in", () => {
    expect(formatAge(null, now)).toBe("sem dados");
    expect(formatAge("2026-11-02T11:59:30Z", now)).toBe("há 30 s");
    expect(formatAge("2026-11-02T11:55:00Z", now)).toBe("há 5 min");
    expect(formatAge("2026-11-02T09:00:00Z", now)).toBe("há 3 h");
  });
  it("ageSeconds uses the same clock", () => {
    expect(ageSeconds("2026-11-02T11:58:30Z", now)).toBe(90);
    expect(ageSeconds(null, now)).toBeNull();
  });
});
