import { describe, expect, it } from "vitest";
import type { HistoryPoint } from "@/lib/api/types";
import { chartAriaLabel } from "./chart-label";

const pts: HistoryPoint[] = [
  { t: "2026-11-02T06:00:00Z", buy: "7320", sell: "7400", mid: "7360" },
  { t: "2026-11-02T09:00:00Z", buy: "7390", sell: "7450", mid: "7420" },
  { t: "2026-11-02T12:00:00Z", buy: "7350", sell: null, mid: "7350" },
];

describe("chartAriaLabel (DS16: rótulo dinâmico)", () => {
  it("descreve par, faixa de compra e janela", () => {
    expect(chartAriaLabel(pts, "PYG", "USD/PYG")).toBe("USD/PYG, compra de 7.320 a 7.390, últimas 6 h");
  });
  it("sem pontos avisa que não há dados", () => {
    expect(chartAriaLabel([], "PYG", "USD/PYG")).toBe("USD/PYG, sem dados no período");
  });
  it("janela curta em minutos", () => {
    expect(chartAriaLabel(pts.slice(0, 1).concat([{ t: "2026-11-02T06:25:00Z", buy: "7330", sell: "7400", mid: "7365" }]), "PYG", "BRL/PYG")).toBe("BRL/PYG, compra de 7.320 a 7.330, últimos 25 min");
  });
});
