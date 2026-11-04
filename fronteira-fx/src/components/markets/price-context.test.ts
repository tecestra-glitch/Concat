import { describe, expect, it } from "vitest";
import type { Quote } from "@/lib/api/types";
import { pickCardContext } from "./price-context";

function q(p: Partial<Quote> & Pick<Quote, "id" | "source_id" | "base" | "quote" | "buy" | "sell" | "modality" | "kind">): Quote {
  return {
    series_key: p.id, branch_id: null, city: null, unit_note: "", amount_base: null, channel: "digital", context: null, fees: [],
    captured_at: "2026-11-02T10:00:00Z", declared_updated_at: null, valid_until: null, evidence_id: null, data_mode: "demo", ...p,
  };
}

const quotes: Quote[] = [
  q({ id: "a", source_id: "chaco", city: "CDE", base: "USD", quote: "PYG", buy: "5905", sell: "5975", modality: "cash", kind: "indicative", channel: "physical" }),
  q({ id: "b", source_id: "alberdi", city: "CDE", base: "USD", quote: "PYG", buy: "5915", sell: "5965", modality: "cash", kind: "indicative", channel: "physical" }),
  // banco demo PY (conta digital) venderia mais barato: contexto diferente, não pode vencer o cartão de balcão.
  q({ id: "c", source_id: "banco-demo-py", base: "USD", quote: "PYG", buy: "5880", sell: "5940", modality: "account", kind: "indicative" }),
  q({ id: "ref", source_id: "bcp", base: "USD", quote: "PYG", buy: "5944.76", sell: "5944.76", modality: "transfer", kind: "market_reference" }),
  // simulador por montante: contexto próprio, fora dos cartões
  q({ id: "wu", source_id: "westernunion", base: "USD", quote: "PYG", buy: null, sell: "5990", modality: "account", kind: "indicative", amount_base: "5000" }),
  q({ id: "n", source_id: "nomad", base: "USD", quote: "BRL", buy: null, sell: "5.431", modality: "account", kind: "indicative" }),
];

describe("pickCardContext", () => {
  it("fixa um único contexto (modalidade) e escolhe melhor compra/venda só dentro dele", () => {
    const ctx = pickCardContext(quotes, { base: "USD", quote: "PYG" });
    expect(ctx.modality).toBe("cash");
    expect(ctx.bestBuy?.source_id).toBe("alberdi");
    expect(ctx.bestSell?.source_id).toBe("alberdi");
    expect(ctx.count).toBe(2);
  });
  it("devolve a referência separada e nunca como melhor preço", () => {
    const ctx = pickCardContext(quotes, { base: "USD", quote: "PYG" });
    expect(ctx.reference?.source_id).toBe("bcp");
    expect([ctx.bestBuy?.source_id, ctx.bestSell?.source_id]).not.toContain("bcp");
  });
  it("ignora cotações dependentes de montante", () => {
    const ctx = pickCardContext(quotes, { base: "USD", quote: "PYG" });
    expect(ctx.bestSell?.source_id).not.toBe("westernunion");
  });
  it("sem balcão, usa a modalidade disponível e aceita lado ausente", () => {
    const ctx = pickCardContext(quotes, { base: "USD", quote: "BRL" });
    expect(ctx.modality).toBe("account");
    expect(ctx.bestBuy).toBeNull();
    expect(ctx.bestSell?.source_id).toBe("nomad");
  });
  it("lista as outras modalidades presentes para o rodapé", () => {
    const ctx = pickCardContext(quotes, { base: "USD", quote: "PYG" });
    expect(ctx.otherModalities).toEqual(["account"]);
  });
  it("par sem cotação devolve contexto vazio", () => {
    const ctx = pickCardContext(quotes, { base: "BRL", quote: "PYG" });
    expect(ctx.modality).toBeNull();
    expect(ctx.count).toBe(0);
  });
});
