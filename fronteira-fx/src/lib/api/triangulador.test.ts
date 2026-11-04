import { describe, expect, it } from "vitest";
import {
  EXECUTABLE_LABEL,
  FxReferenceSchema,
  IndicatorsSchema,
  REFERENCE_LABEL,
  ReferenceQuoteSchema,
  SentimentSchema,
  currencyOfNode,
  formatReferencePrice,
  triangleIsExecutable,
  venueOfNode,
} from "./triangulador";
import { demoCryptoRefs, demoFxRefs, demoIndicators, demoMacroRefs, demoSentiment } from "./demo-triangulador";

describe("rótulo executável x referência", () => {
  it("só cotação firme (quoted) é executável", () => {
    expect(triangleIsExecutable({ confidence: "quoted" })).toBe(true);
    expect(triangleIsExecutable({ confidence: "estimated" })).toBe(false);
    expect(triangleIsExecutable({ confidence: "incomplete" })).toBe(false);
  });

  it("os rótulos são os textos fixos da regra", () => {
    expect(EXECUTABLE_LABEL).toBe("Executável");
    expect(REFERENCE_LABEL).toBe("Referência · não executável");
  });
});

describe("contratos de referência", () => {
  it("recusa qualquer referência marcada como executável", () => {
    const bad = { ...demoCryptoRefs[0], executable: true };
    expect(ReferenceQuoteSchema.safeParse(bad).success).toBe(false);
  });

  it("câmbio de referência precisa de referencia=true e executable=false", () => {
    expect(FxReferenceSchema.safeParse({ ...demoFxRefs[0], referencia: false }).success).toBe(false);
    expect(FxReferenceSchema.safeParse({ ...demoFxRefs[0], executable: true }).success).toBe(false);
  });

  it("indicador e sentimento são sempre não executáveis", () => {
    expect(IndicatorsSchema.safeParse({ ...demoIndicators("BTC/USDT", "5m"), executable: true }).success).toBe(false);
    expect(SentimentSchema.safeParse({ ...demoSentiment[0], executable: true }).success).toBe(false);
  });

  it("os dados de demonstração passam pelos próprios contratos", () => {
    for (const q of [...demoCryptoRefs, ...demoMacroRefs]) expect(ReferenceQuoteSchema.safeParse(q).success).toBe(true);
    for (const r of demoFxRefs) expect(FxReferenceSchema.safeParse(r).success).toBe(true);
    expect(IndicatorsSchema.safeParse(demoIndicators("ETH/USDT", "1d")).success).toBe(true);
    for (const s of demoSentiment) expect(SentimentSchema.safeParse(s).success).toBe(true);
  });
});

describe("nós e preços", () => {
  it("separa moeda e local de um nó moeda@local", () => {
    expect(currencyOfNode("BRL@casa-a")).toBe("BRL");
    expect(venueOfNode("BRL@casa-a")).toBe("casa-a");
    expect(venueOfNode("USDT")).toBe("");
  });

  it("preço de referência mantém casas e nunca vira zero quando inválido", () => {
    expect(formatReferencePrice("5.4530")).toBe("5,4530");
    expect(formatReferencePrice("76006.95")).toBe("76.006,95");
    expect(formatReferencePrice("abc")).toBe("—");
  });
});
