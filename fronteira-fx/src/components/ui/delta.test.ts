import { describe, expect, it } from "vitest";
import { describeDelta } from "./delta";

describe("describeDelta (sinal + seta + texto, nunca só cor)", () => {
  it("positivo sobe", () => expect(describeDelta("0.0041")).toEqual({ direction: "up", arrow: "▲", srText: "subiu" }));
  it("negativo cai", () => expect(describeDelta(-2)).toEqual({ direction: "down", arrow: "▼", srText: "caiu" }));
  it("zero é estável", () => expect(describeDelta("0")).toEqual({ direction: "flat", arrow: "", srText: "estável" }));
  it("sem valor é indefinido", () => expect(describeDelta(null)).toEqual({ direction: "none", arrow: "", srText: "sem variação conhecida" }));
});
