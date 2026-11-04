import { describe, expect, it } from "vitest";
import { demoNewsList, demoQuotes, demoVolatility, demoNews } from "./demo-market";
import { MarketQuoteListSchema, MarketVolatilityListSchema, NewsListSchema, REFERENCE_NOTE } from "./market";

describe("contrato do módulo market (espelho dos schemas do backend)", () => {
  it("a demonstração respeita o contrato: referência, nunca executável, sempre modo demo", () => {
    expect(MarketQuoteListSchema.safeParse(demoQuotes).success).toBe(true);
    expect(MarketVolatilityListSchema.safeParse(demoVolatility).success).toBe(true);
    expect(NewsListSchema.safeParse(demoNews).success).toBe(true);
    for (const q of demoQuotes) {
      expect(q.executable).toBe(false);
      expect(q.note).toBe(REFERENCE_NOTE);
      expect(q.data_mode).toBe("demo");
    }
  });

  it("rejeita preço que não é string decimal (dinheiro nunca trafega como número)", () => {
    const bad = { ...demoQuotes[0], price: 5.5179 as unknown as string };
    expect(MarketQuoteListSchema.safeParse([bad]).success).toBe(false);
  });

  it("rejeita quote marcada como executável", () => {
    const bad = { ...demoQuotes[0], executable: true };
    expect(MarketQuoteListSchema.safeParse([bad]).success).toBe(false);
  });

  it("rejeita regime fora do selo normal / alta / muito alta", () => {
    const bad = { ...demoVolatility[0], regime: "extrema" };
    expect(MarketVolatilityListSchema.safeParse([bad]).success).toBe(false);
  });
});

describe("demonstração de notícias", () => {
  it("é ilustrativa, usa links .invalid e nunca aponta para veículo real", () => {
    for (const n of demoNews) {
      expect(n.source).toBe("demo");
      expect(n.link.startsWith("https://demo.invalid/")).toBe(true);
      expect(n.title.startsWith("Demonstração")).toBe(true);
    }
  });

  it("exige atribuição em cada manchete (contrato do backend)", () => {
    const semAtribuicao = { ...demoNews[0], attribution: undefined };
    expect(NewsListSchema.safeParse([semAtribuicao]).success).toBe(false);
  });

  it("aceita manchete do investinglive com trecho curto e atribuição", () => {
    const il = {
      ...demoNews[0],
      id: "il-1",
      source: "investinglive",
      feed: "investinglive",
      data_mode: "real",
      title: "Exemplo: PMI de serviços",
      link: "https://investinglive.com/news/exemplo/",
      excerpt: "Anterior 51,7.",
      attribution: "Fonte: Investinglive.com (copyright Investinglive.com). Link para a matéria original.",
    };
    expect(NewsListSchema.safeParse([il]).success).toBe(true);
  });

  it("filtra por fonte e respeita o limite", () => {
    expect(demoNewsList({ source: "bcb" })).toHaveLength(0);
    expect(demoNewsList({ source: "all", limit: 2 })).toHaveLength(2);
    expect(demoNewsList({ source: "demo" }).length).toBe(demoNews.length);
  });
});
