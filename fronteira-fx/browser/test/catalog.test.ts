import { describe, expect, it } from "vitest";
import { catalogAmount, catalogShape, isCatalogUrl, quoteFromCatalog, sameAmount } from "../src/catalog.js";

// Synthetic response: the field names are a guess (see src/catalog.ts). No identifiers, tokens or e-mails.
const SAMPLE = {
  services_groups: [
    {
      pay_groups: [
        { fund_in: "CARD", fund_out: "AG", receive_amount: "5328209.00", fee_brl: "0.00" },
        {
          fund_in: "WUPAY",
          fund_out: "BA",
          receive_amount: "5401871.00",
          fee_brl: "0.00",
          fee_before_discount_brl: "45.00",
          exchange_rate: "1080.3741",
          delivery: "0-4 Dias úteis",
          promo: "100% de desconto 45.00 BRL",
        },
        {
          fund_in: "WUPAY",
          fund_out: "AG",
          receive_amount: "5328209.00",
          fee_brl: "0.00",
          fee_before_discount_brl: "55.00",
          exchange_rate: "1065.6418",
          delivery: "Em minutos",
          promo: "100% de desconto 55.00 BRL",
        },
      ],
    },
  ],
};

describe("quoteFromCatalog", () => {
  it("escolhe a combinação de recebimento e pagamento pedida", () => {
    const q = quoteFromCatalog(SAMPLE, { receive: "bank_account", payment: "pix" });
    expect(q).toEqual({
      receive_amount_pyg: "5401871.00",
      fee_brl: "0.00",
      fee_before_discount_brl: "45.00",
      exchange_rate: "1080.3741",
      delivery: "0-4 Dias úteis",
      promo: "100% de desconto 45.00 BRL",
    });
  });

  it("recebimento em dinheiro usa a combinação de agência", () => {
    const q = quoteFromCatalog(SAMPLE, { receive: "cash_pickup", payment: "pix" });
    expect(q?.receive_amount_pyg).toBe("5328209.00");
    expect(q?.delivery).toBe("Em minutos");
  });

  it("devolve null quando nenhuma combinação bate com o pedido", () => {
    expect(quoteFromCatalog(SAMPLE, { receive: "bank_account", payment: "card" })).toBeNull();
  });

  it("devolve null quando a resposta não tem combinações de pagamento", () => {
    expect(quoteFromCatalog({ services_groups: [] }, { receive: "bank_account", payment: "pix" })).toBeNull();
    expect(quoteFromCatalog(null, { receive: "bank_account", payment: "pix" })).toBeNull();
  });

  it("não aceita valor recebido zero", () => {
    const zero = { pay_groups: [{ fund_in: "WUPAY", fund_out: "BA", receive_amount: "0.00" }] };
    expect(quoteFromCatalog(zero, { receive: "bank_account", payment: "pix" })).toBeNull();
  });
});

describe("catalogShape (diagnóstico sem valores)", () => {
  it("mostra chaves e tipos, nunca os valores", () => {
    const shape = catalogShape(SAMPLE);
    expect(shape).toContain("services_groups");
    expect(shape).toContain("fund_in:string");
    expect(shape).not.toContain("5401871");
    expect(shape).not.toContain("WUPAY");
  });

  it("limita o tamanho", () => {
    const big: Record<string, unknown> = {};
    for (let i = 0; i < 40; i++) big[`k${i}`] = { a: { b: { c: { d: 1 } } } };
    expect(catalogShape(big).length).toBeLessThanOrEqual(601);
  });
});

describe("isCatalogUrl e catalogAmount", () => {
  it("reconhece só a chamada de cotação do site", () => {
    expect(isCatalogUrl("https://www.westernunion.com/wuconnect/prices/catalog")).toBe(true);
    expect(isCatalogUrl("https://www.westernunion.com/wuconnect/prices/catalog?x=1")).toBe(true);
    expect(isCatalogUrl("https://evil.example/wuconnect/prices/catalog")).toBe(false);
    expect(isCatalogUrl("https://www.westernunion.com/img/logo.png")).toBe(false);
    expect(isCatalogUrl("nao e url")).toBe(false);
  });

  it("lê o valor enviado do corpo da requisição", () => {
    const body = JSON.stringify({ sender: { cty_iso2_ext: "BR", curr_iso3: "BRL", send_amount: "5000" } });
    expect(catalogAmount(body)).toBe("5000");
    expect(catalogAmount(JSON.stringify({ sender: { send_amount: 5000 } }))).toBe("5000");
    expect(catalogAmount("não é json")).toBeNull();
    expect(catalogAmount(null)).toBeNull();
    expect(catalogAmount(JSON.stringify({ sender: {} }))).toBeNull();
  });

  it("compara valores como número (5000 e 5000.00 são o mesmo)", () => {
    expect(sameAmount("5000", "5000.00")).toBe(true);
    expect(sameAmount("5000", "5001")).toBe(false);
    expect(sameAmount("abc", "5000")).toBe(false);
  });
});
