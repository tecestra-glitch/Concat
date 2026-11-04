import { describe, expect, it } from "vitest";
import { runWesternUnionFlow, type FlowInput, type FlowOptions } from "../src/flow.js";
import { Trail } from "../src/trail.js";
import { FakeWuPage, LIVE_BODY, type FakeOptions } from "./fake-page.js";

const NOW = new Date("2026-11-04T12:00:00.000Z");
const INPUT: FlowInput = { amount_brl: "5000", payment: "pix", receive: "bank_account" };
const STAMPED = /@\d+\.\ds$/;

// Synthetic price response (no identifiers, tokens or e-mails). Shape is a guess until the first live capture.
const CATALOG_OK = {
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
      ],
    },
  ],
};

const CATALOG_OTHER_ONLY = {
  services_groups: [{ pay_groups: [{ fund_in: "CARD", fund_out: "AG", receive_amount: "5328209.00" }] }],
};

function labelsOf(steps: string[]): string[] {
  return steps.map((s) => s.replace(STAMPED, ""));
}

async function run(opts: FakeOptions, input: FlowInput = INPUT, flow: FlowOptions = {}) {
  const page = new FakeWuPage(opts);
  const trail = flow.trail ?? new Trail();
  const result = await runWesternUnionFlow(page, input, NOW, { ...flow, trail });
  return { page, result };
}

describe("runWesternUnionFlow com página simulada (caminho de cliques)", () => {
  it("monta o scenario com as chaves que o parse() do Python espera", async () => {
    const { result, page } = await run({}, INPUT, { screenshot: true });
    expect(result.status).toBe("ok");
    expect(result.source).toBe("clicks");
    const sc = result.scenario;
    if (sc === null) throw new Error("scenario ausente num fluxo ok");
    expect(Object.keys(sc).sort()).toEqual(SCENARIO_KEYS.slice().sort());
    expect(sc.origin).toBe("BR");
    expect(sc.destination).toBe("PY");
    expect(sc.send_currency).toBe("BRL");
    expect(sc.receive_currency).toBe("PYG");
    expect(sc.amount_brl).toBe("5000");
    expect(sc.payment).toBe("pix");
    expect(sc.receive).toBe("bank_account");
    expect(sc.bank).toBeNull();
    expect(sc.channel).toBe("web");
    expect(sc.captured_at).toBe(NOW.toISOString());
    expect(sc.receive_amount_pyg).toBe("5401871.00");
    expect(sc.receive_amount_text).toBe("5,401,871.00");
    expect(sc.fee_brl).toBe("0.00");
    expect(sc.fee_before_discount_brl).toBe("45.00");
    expect(sc.exchange_rate).toBe("1,080.3741");
    expect(sc.promo).toBe("100% de desconto 45.00 BRL");
    expect(result.screenshot).not.toBeNull();
    expect(labelsOf(result.trail)).toContain("amount=5000");
    expect(labelsOf(result.trail)).toContain("receive=5,401,871.00");
    expect(sc.summary_text).toContain("RESUMO");
    expect(page.calls).toContain('click:[amplitude-id="tile-fundsin-wupay"]');
  });

  it("cada passo da trilha leva o tempo desde o início", async () => {
    let ms = 0;
    const trail = new Trail(() => ms);
    const page = new FakeWuPage({});
    const originalGoto = page.goto.bind(page);
    page.goto = async () => {
      ms = 1_200;
      return originalGoto();
    };
    const result = await runWesternUnionFlow(page, INPUT, NOW, { trail });
    expect(result.status).toBe("ok");
    expect(result.trail[0]).toBe("goto=200@1.2s");
    for (const step of result.trail) expect(step).toMatch(STAMPED);
  });

  it("não tira captura quando a chamada não pediu screenshot", async () => {
    const { result, page } = await run({});
    expect(result.status).toBe("ok");
    expect(result.screenshot).toBeNull();
    expect(page.calls).not.toContain("screenshot");
  });

  it("escolhe o recebimento em dinheiro pelo tile de agência", async () => {
    const { result, page } = await run({ receiveText: "5,328,209.00" }, { ...INPUT, receive: "cash_pickup" });
    expect(result.status).toBe("ok");
    expect(result.scenario?.receive).toBe("cash_pickup");
    expect(result.scenario?.receive_amount_pyg).toBe("5328209.00");
    expect(page.calls).toContain('click:[amplitude-id="tile-fundsout-ag"]');
  });

  it("repete o clique no tile de recebimento (2 vezes) quando os tiles de pagamento não aparecem", async () => {
    const { result } = await run({ paymentOffered: false });
    expect(result.status).toBe("degraded");
    expect(result.message).toContain("payment option for 'pix' not offered");
    expect(labelsOf(result.trail).filter((t) => t.startsWith("receive-again")).length).toBe(2);
  });

  it("devolve blocked com HTTP 403 na página inicial, sem scenario", async () => {
    const { result } = await run({ status: 403 });
    expect(result.status).toBe("blocked");
    expect(result.scenario).toBeNull();
    expect(result.message).toContain("HTTP 403");
    expect(result.trail).toHaveLength(1);
    expect(result.trail[0]).toMatch(/^goto=403@\d+\.\ds$/);
  });

  it("devolve blocked quando a página de bloqueio aparece no lugar dos tiles", async () => {
    const { result } = await run({ countryTile: false, body: "Access Denied. Unusual traffic detected." });
    expect(result.status).toBe("blocked");
    expect(result.message).toContain("anti-bot page instead of country tiles");
  });

  it("devolve degraded (sem bloqueio) quando o tile do país some", async () => {
    const { result } = await run({ countryTile: false, body: "Página nova sem nada conhecido" });
    expect(result.status).toBe("degraded");
    expect(result.message).toContain("country tile 'Paraguai' not found");
  });

  it("devolve degraded quando o valor é zerado pelo SPA nas três tentativas", async () => {
    const { result, page } = await run({ amountSticks: false });
    expect(result.status).toBe("degraded");
    expect(result.message).toContain("amount did not stick");
    expect(labelsOf(result.trail).filter((t) => t.startsWith("amount-reset")).length).toBe(3);
    expect(page.calls.filter((c) => c === "Tab").length).toBe(3);
  });

  it("devolve degraded quando a opção de recebimento não existe", async () => {
    const { result } = await run({ receiveOffered: false });
    expect(result.status).toBe("degraded");
    expect(result.message).toContain("receive option for 'bank_account' not found");
  });

  it("devolve degraded quando o valor recebido nunca aparece", async () => {
    const { result } = await run({ quoteAppears: false });
    expect(result.status).toBe("degraded");
    expect(result.message).toContain("receive amount never populated");
  });

  it("nunca usa o texto de bloqueio como cotação e nunca grava cookies no resultado", async () => {
    const { result } = await run({});
    const serialised = JSON.stringify(result);
    expect(serialised).not.toMatch(/cookie|set-cookie|authorization/i);
    expect(LIVE_BODY).toContain("RESUMO");
  });
});

describe("runWesternUnionFlow: cotação pela resposta do site (prices/catalog)", () => {
  it("monta o scenario da resposta e não clica nos tiles de recebimento e pagamento", async () => {
    const { result, page } = await run({ catalog: CATALOG_OK });
    expect(result.status).toBe("ok");
    expect(result.source).toBe("catalog");
    expect(page.calls).not.toContain('click:[amplitude-id="tile-fundsout-ba"]');
    expect(page.calls).not.toContain('click:[amplitude-id="tile-fundsin-wupay"]');
    const sc = result.scenario;
    if (sc === null) throw new Error("scenario ausente");
    expect(Object.keys(sc).sort()).toEqual(SCENARIO_KEYS.slice().sort());
    expect(sc.receive_amount_pyg).toBe("5401871.00");
    expect(sc.fee_brl).toBe("0.00");
    expect(sc.fee_before_discount_brl).toBe("45.00");
    expect(sc.exchange_rate).toBe("1080.3741");
    expect(sc.delivery).toBe("0-4 Dias úteis");
    expect(sc.promo).toBe("100% de desconto 45.00 BRL");
    expect(sc.amount_brl).toBe("5000");
    expect(labelsOf(result.trail)).toContain("catalog:ok");
    expect(labelsOf(result.trail).some((t) => t.startsWith("receive=5401871.00"))).toBe(true);
  });

  it("cai para os cliques quando a resposta não traz a combinação pedida", async () => {
    const { result, page } = await run({ catalog: CATALOG_OTHER_ONLY });
    expect(result.status).toBe("ok");
    expect(result.source).toBe("clicks");
    expect(labelsOf(result.trail).some((t) => t.startsWith("catalog:no-match("))).toBe(true);
    expect(page.calls).toContain('click:[amplitude-id="tile-fundsout-ba"]');
  });

  it("cai para os cliques quando a resposta não chega", async () => {
    const { result } = await run({});
    expect(result.source).toBe("clicks");
    expect(labelsOf(result.trail)).toContain("catalog:not-seen");
  });

  it("o diagnóstico da resposta não-casada tem só chaves e tipos, sem valores", async () => {
    const { result } = await run({ catalog: CATALOG_OTHER_ONLY });
    const diag = result.trail.find((t) => t.startsWith("catalog:no-match(")) ?? "";
    expect(diag).toContain("fund_in:string");
    expect(diag).not.toContain("CARD");
    expect(diag).not.toContain("5328209");
  });
});

// The same keys the click path builds (scenario base + extractSummary + receive fields).
const SCENARIO_KEYS = [
  "origin", "destination", "send_currency", "receive_currency", "amount_brl", "payment", "receive", "bank",
  "channel", "promo", "captured_at", "receive_amount_pyg", "receive_amount_text", "fee_brl",
  "fee_before_discount_brl", "exchange_rate", "delivery", "summary_text",
];
