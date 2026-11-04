import { afterEach, beforeEach, describe, expect, it } from "vitest";
import handler from "../api/westernunion.js";
import { handleWesternUnion, type HandlerDeps } from "../src/handler.js";
import type { OpenedPage } from "../src/playwright-page.js";
import { FakeWuPage, type FakeOptions } from "./fake-page.js";

const SECRET = "segredo-de-teste-123"; // test value only; never a real credential
const ENV = { BROWSER_SECRET: SECRET };
const GOOD_BODY = { amount_brl: "5000", payment: "pix", receive: "bank_account" };
const NOW = new Date("2026-11-04T12:00:00.000Z");

function deps(opts: FakeOptions = {}, extra: Partial<HandlerDeps> = {}) {
  const state = { closed: 0, page: null as FakeWuPage | null };
  const d: HandlerDeps = {
    now: () => NOW,
    budgetMs: 5_000,
    open: async (): Promise<OpenedPage> => {
      const page = new FakeWuPage(opts);
      state.page = page;
      return {
        page,
        close: async () => {
          state.closed += 1;
        },
      };
    },
    ...extra,
  };
  return { d, state };
}

const auth = { authorization: `Bearer ${SECRET}` };

describe("handleWesternUnion: autenticação e método", () => {
  it("404 quando BROWSER_SECRET não está configurado (ou é placeholder)", async () => {
    const { d } = deps();
    expect((await handleWesternUnion({ method: "POST", ...auth, body: GOOD_BODY }, {}, d)).status).toBe(404);
    expect(
      (await handleWesternUnion({ method: "POST", ...auth, body: GOOD_BODY }, { BROWSER_SECRET: "TROQUE_X" }, d)).status,
    ).toBe(404);
  });

  it("405 para qualquer método que não seja POST", async () => {
    const { d } = deps();
    const res = await handleWesternUnion({ method: "GET", ...auth, body: GOOD_BODY }, ENV, d);
    expect(res.status).toBe(405);
    expect(res.headers?.Allow).toBe("POST");
  });

  it("401 sem Authorization e com segredo errado", async () => {
    const { d, state } = deps();
    expect((await handleWesternUnion({ method: "POST", body: GOOD_BODY }, ENV, d)).status).toBe(401);
    expect(
      (await handleWesternUnion({ method: "POST", authorization: "Bearer errado", body: GOOD_BODY }, ENV, d)).status,
    ).toBe(401);
    expect(state.page).toBeNull(); // nunca abre o navegador sem autenticação
  });
});

describe("handleWesternUnion: validação do corpo", () => {
  it.each([
    ["URL do cliente", { ...GOOD_BODY, url: "https://evil.example" }],
    ["valor zero", { ...GOOD_BODY, amount_brl: "0" }],
    ["valor acima do limite", { ...GOOD_BODY, amount_brl: "100001" }],
    ["valor com vírgula", { ...GOOD_BODY, amount_brl: "5000,00" }],
    ["pagamento desconhecido", { ...GOOD_BODY, payment: "boleto" }],
    ["recebimento desconhecido", { ...GOOD_BODY, receive: "wallet" }],
    ["banco com markup", { ...GOOD_BODY, bank: "<script>x</script>" }],
    ["corpo ausente", undefined],
  ])("400 para %s", async (_name, body) => {
    const { d, state } = deps();
    const res = await handleWesternUnion({ method: "POST", ...auth, body }, ENV, d);
    expect(res.status).toBe(400);
    expect(res.body.error).toBe("invalid_request");
    expect(state.page).toBeNull();
  });

  it("aceita valor no limite, pagamento card e banco curto", async () => {
    const { d } = deps();
    const res = await handleWesternUnion(
      { method: "POST", ...auth, body: { amount_brl: "100000", payment: "card", receive: "cash_pickup", bank: "Itaú" } },
      ENV,
      d,
    );
    expect(res.status).toBe(200);
  });
});

describe("handleWesternUnion: execução", () => {
  it("200 com scenario, trail e status ok, sem screenshot quando não pedida", async () => {
    const { d, state } = deps();
    const res = await handleWesternUnion({ method: "POST", ...auth, body: GOOD_BODY }, ENV, d);
    expect(res.status).toBe(200);
    expect(res.body.status).toBe("ok");
    expect(Array.isArray(res.body.trail)).toBe(true);
    expect((res.body.scenario as { receive_amount_pyg: string }).receive_amount_pyg).toBe("5401871.00");
    expect(res.body).not.toHaveProperty("screenshot_png_b64");
    expect(state.closed).toBe(1);
  });

  it("inclui screenshot_png_b64 quando pedida", async () => {
    const { d } = deps();
    const res = await handleWesternUnion({ method: "POST", ...auth, body: { ...GOOD_BODY, screenshot: true } }, ENV, d);
    const b64 = res.body.screenshot_png_b64 as string;
    expect(Buffer.from(b64, "base64").subarray(0, 4).toString("hex")).toBe("89504e47");
  });

  it("resposta de bloqueio (403) sem scenario e com o fechamento do navegador", async () => {
    const { d, state } = deps({ status: 403 });
    const res = await handleWesternUnion({ method: "POST", ...auth, body: GOOD_BODY }, ENV, d);
    expect(res.status).toBe(200);
    expect(res.body.status).toBe("blocked");
    expect(res.body.scenario).toBeNull();
    expect(state.closed).toBe(1);
  });

  it("devolve status error (HTTP 200) quando o Chromium não abre", async () => {
    const { d } = deps({}, {
      open: async () => {
        throw new Error("launch failed");
      },
    });
    const res = await handleWesternUnion({ method: "POST", ...auth, body: GOOD_BODY }, ENV, d);
    expect(res.status).toBe(200);
    expect(res.body.status).toBe("error");
  });

  it("corta a execução no orçamento de tempo e reporta degraded", async () => {
    const { d, state } = deps({ hang: true }, { budgetMs: 20 });
    const res = await handleWesternUnion({ method: "POST", ...auth, body: GOOD_BODY }, ENV, d);
    expect(res.body.status).toBe("degraded");
    expect(String(res.body.message)).toContain("deadline");
    expect(state.closed).toBe(1);
  });
});

describe("api/westernunion.ts (wrapper Vercel)", () => {
  let saved: string | undefined;
  beforeEach(() => {
    saved = process.env.BROWSER_SECRET;
    delete process.env.BROWSER_SECRET;
  });
  afterEach(() => {
    if (saved === undefined) delete process.env.BROWSER_SECRET;
    else process.env.BROWSER_SECRET = saved;
  });

  function fakeRes() {
    const headers: Record<string, string> = {};
    const out = { statusCode: 0, body: "" };
    return {
      out,
      headers,
      res: {
        set statusCode(v: number) {
          out.statusCode = v;
        },
        get statusCode() {
          return out.statusCode;
        },
        setHeader(name: string, value: string) {
          headers[name.toLowerCase()] = value;
        },
        end(chunk: string) {
          out.body = chunk;
        },
      },
    };
  }

  it("responde 404 JSON quando o segredo não existe no ambiente", async () => {
    const { res, out, headers } = fakeRes();
    const req = { method: "POST", headers: {}, body: GOOD_BODY };
    await handler(req as never, res as never);
    expect(out.statusCode).toBe(404);
    expect(headers["content-type"]).toContain("application/json");
    expect(headers["cache-control"]).toBe("no-store");
    expect(JSON.parse(out.body)).toEqual({ error: "not_found" });
  });

  it("aceita o corpo como string JSON quando o runtime não o pré-analisa", async () => {
    process.env.BROWSER_SECRET = SECRET;
    const { res, out } = fakeRes();
    const req = { method: "POST", headers: { authorization: "Bearer errado" }, body: JSON.stringify(GOOD_BODY) };
    await handler(req as never, res as never);
    expect(out.statusCode).toBe(401);
  });
});
