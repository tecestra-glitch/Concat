import { describe, expect, it } from "vitest";
import type { Cycle } from "@/lib/api/types";
import { cycleCurrency, formatMinutes, isProfitable } from "./cycle-helpers";

const base: Cycle = { start: "BRL@brbank", path: [], edges: [], amount_in: "25000", amount_out: "25041.20", gain: "41.20", roi: "0.001648", minutes: 4320, confidence: "estimated", data_mode: "real" };

describe("cycle helpers (D1: strings decimais)", () => {
  it("moeda do nó inicial", () => {
    expect(cycleCurrency("BRL@brbank")).toBe("BRL");
    expect(cycleCurrency("PYG@chaco:CDE")).toBe("PYG");
  });
  it("lucro comparado como número, não como string", () => {
    expect(isProfitable(base)).toBe(true);
    expect(isProfitable({ ...base, gain: "0" })).toBe(false);
    expect(isProfitable({ ...base, gain: "-0.5" })).toBe(false);
    // "9" > "10" seria verdadeiro em comparação de strings
    expect(isProfitable({ ...base, gain: "0.0000001" })).toBe(true);
  });
  it("prazo em dias a partir de 24 h, senão minutos", () => {
    expect(formatMinutes(4320)).toBe("3,0 d");
    expect(formatMinutes(90)).toBe("90 min");
  });
});
