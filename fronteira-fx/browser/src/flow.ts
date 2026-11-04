// Port of `WesternUnionAdapter.fetch` (backend/src/fronteira_fx/adapters/westernunion.py): same selectors, labels,
// waits, cookie banner handling, block detection and repeated clicks. The result is the `scenario` document that the
// Python `parse()` consumes. Nothing here moves money: it only reads a public quote simulator.

import { parseDecimalText } from "./decimal.js";
import { extractSummary, looksBlocked } from "./summary.js";

export const START_URL = "https://www.westernunion.com/br/pt/web/send-money/start";
export const STEP_TIMEOUT_MS = 30_000;

export type Payment = "pix" | "bank_transfer" | "card";
export type Receive = "bank_account" | "cash_pickup";

export const SELECTORS = {
  country_tile: 'button[amplitude-id="tile-country-selection"]',
  send_amount: "#txtSendAmount",
  receive_amount: "#txtReceiveAmount",
  currency_select: "#wu-currency-select",
  cookie_close: "button.onetrust-close-btn-handler, #onetrust-accept-btn-handler",
  // Selectors used inside predicates evaluated in the page (also reused by the test double).
  fundsout_any: '[amplitude-id^="tile-fundsout"]',
  fundsin_any: '[amplitude-id^="tile-fundsin"]',
} as const;

export const RECEIVE_TILES: Record<Receive, readonly string[]> = {
  bank_account: ['[amplitude-id="tile-fundsout-ba"]', "#fundsOut_BA"],
  cash_pickup: ['[amplitude-id="tile-fundsout-ag"]', "#fundsOut_AG"],
};
export const RECEIVE_LABELS: Record<Receive, readonly string[]> = {
  bank_account: ["conta bancaria", "conta bancária", "bank account"],
  cash_pickup: ["receber em dinheiro", "em uma loja", "cash pickup"],
};
export const PAYMENT_TILES: Record<Payment, readonly string[]> = {
  pix: ['[amplitude-id="tile-fundsin-wupay"]', "#fundsIn_WUPay"],
  bank_transfer: ['[amplitude-id="tile-fundsin-wupay"]', "#fundsIn_WUPay"],
  card: ['[amplitude-id="tile-fundsin-cc"]', '[amplitude-id="tile-fundsin-dc"]', '[amplitude-id^="tile-fundsin-c"]'],
};
export const PAYMENT_LABELS: Record<Payment, readonly string[]> = {
  pix: ["pix"],
  bank_transfer: ["transferência bancária", "transferencia bancaria", "bank transfer"],
  card: ["cartão", "cartao", "card"],
};

export class FlowTimeout extends Error {
  constructor(message = "timeout") {
    super(message);
    this.name = "FlowTimeout";
  }
}

/** The subset of page operations the flow needs. Playwright implements it in production; tests use a fake. */
export interface FlowPage {
  /** Returns the HTTP status of the main document, or null. */
  goto(url: string, timeoutMs: number): Promise<number | null>;
  /** Waits until a matching element is visible; throws FlowTimeout otherwise. */
  waitFor(selector: string, timeoutMs: number, hasText?: string): Promise<void>;
  /** Clicks the first matching element; throws FlowTimeout when it cannot be clicked in time. */
  click(selector: string, timeoutMs: number, hasText?: string): Promise<void>;
  /** Waits for, then clicks, the first element whose text matches `label` (case-insensitive). */
  clickByText(label: string, timeoutMs: number): Promise<void>;
  waitForText(pattern: string, timeoutMs: number): Promise<void>;
  fill(selector: string, value: string): Promise<void>;
  pressTab(): Promise<void>;
  selectOption(selector: string, value: string, timeoutMs: number): Promise<void>;
  /** Evaluates a self-contained predicate (source text, `(arg) => boolean`) in the page until true; throws FlowTimeout. */
  waitForFunction(source: string, arg: unknown, timeoutMs: number): Promise<void>;
  inputValue(selector: string): Promise<string>;
  bodyText(): Promise<string>;
  screenshot(): Promise<Uint8Array>;
  wait(ms: number): Promise<void>;
}

export interface Scenario {
  origin: string;
  destination: string;
  send_currency: string;
  receive_currency: string;
  amount_brl: string;
  payment: Payment;
  receive: Receive;
  bank: string | null;
  channel: string;
  promo: string | null;
  captured_at: string;
  receive_amount_pyg?: string | null;
  receive_amount_text?: string;
  fee_brl?: string | null;
  fee_before_discount_brl?: string | null;
  exchange_rate?: string | null;
  delivery?: string | null;
  summary_text?: string;
}

export type FlowStatus = "ok" | "degraded" | "blocked" | "error";

export interface FlowResult {
  status: FlowStatus;
  message: string;
  trail: string[];
  scenario: Scenario | null;
  screenshot: Uint8Array | null;
}

export interface FlowInput {
  amount_brl: string;
  payment: Payment;
  receive: Receive;
  bank?: string | undefined;
}

// Predicates run inside the page. They are plain source strings with no closures and no helpers, so the same text
// works for Playwright, for any bundler (no injected `__name` helpers) and for the test double.
export const AMOUNT_READY_SRC = `(arg) => {
  const doc = globalThis.document;
  const el = doc.querySelector(arg.sel);
  return !!el && (el.value || "").replace(/[^0-9.]/g, "").startsWith(arg.want) && !!doc.querySelector(arg.tile);
}`;

export const RECEIVE_POPULATED_SRC = `(arg) => {
  const el = globalThis.document.querySelector(arg.sel);
  return !!(el && el.value && el.value !== "0.00");
}`;

function escapeRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export { escapeRegExp };

export interface FlowOptions {
  /** Test-only override of the start page. The HTTP handler never sets it: the function opens START_URL only. */
  startUrl?: string;
  /** Shared step list, so a caller that cuts the run short (deadline) still sees the steps taken so far. */
  trail?: string[];
}

export async function runWesternUnionFlow(
  page: FlowPage,
  input: FlowInput,
  now: Date,
  options: FlowOptions = {},
): Promise<FlowResult> {
  const { amount_brl: amount, payment, receive, bank } = input;
  const trail: string[] = options.trail ?? [];
  const startUrl = options.startUrl ?? START_URL;
  const scenario: Scenario = {
    origin: "BR",
    destination: "PY",
    send_currency: "BRL",
    receive_currency: "PYG",
    amount_brl: amount,
    payment,
    receive,
    bank: bank ?? null,
    channel: "web",
    promo: null,
    captured_at: now.toISOString(),
  };
  let shot: Uint8Array | null = null;

  const fail = async (status: FlowStatus, reason: string): Promise<FlowResult> => {
    if (shot === null) {
      try {
        shot = await page.screenshot();
      } catch {
        shot = null; // evidence is best effort
      }
    }
    return { status, message: `${reason}; steps: ${trail.join(" > ")}`, trail, scenario: null, screenshot: shot };
  };

  // Tries each selector (the first with the full timeout, the rest briefly), then the visible labels.
  const clickFirst = async (selectors: readonly string[], labels: readonly string[], what: string): Promise<boolean> => {
    for (let i = 0; i < selectors.length; i++) {
      const sel = selectors[i] as string;
      try {
        await page.waitFor(sel, i === 0 ? STEP_TIMEOUT_MS : 2_000);
        await page.click(sel, STEP_TIMEOUT_MS);
        trail.push(`${what}:${sel}`);
        return true;
      } catch (err) {
        if (!(err instanceof FlowTimeout)) throw err;
      }
    }
    for (const label of labels) {
      try {
        await page.clickByText(label, 2_000);
        trail.push(`${what}:text=${label}`);
        return true;
      } catch (err) {
        if (!(err instanceof FlowTimeout)) throw err;
      }
    }
    return false;
  };

  try {
    const status = await page.goto(startUrl, 60_000);
    trail.push(`goto=${status ?? "None"}`);
    if (status === 403 || status === 429 || status === 503) {
      return await fail("blocked", `HTTP ${status} on start page (anti-bot)`);
    }

    // 1) destination country
    try {
      await page.waitFor(SELECTORS.country_tile, STEP_TIMEOUT_MS, "Paraguai");
      await page.click(SELECTORS.country_tile, STEP_TIMEOUT_MS, "Paraguai");
      trail.push("tile:Paraguai");
    } catch (err) {
      if (!(err instanceof FlowTimeout)) throw err;
      const body = (await page.bodyText()).slice(0, 600);
      if (looksBlocked(body)) return await fail("blocked", "anti-bot page instead of country tiles");
      return await fail("degraded", "country tile 'Paraguai' not found (selector drift?)");
    }
    try {
      await page.click(SELECTORS.cookie_close, 3_000);
      trail.push("cookies:closed");
    } catch {
      // the banner is optional
    }

    // 2) amount + currency
    try {
      await page.waitFor(SELECTORS.send_amount, STEP_TIMEOUT_MS);
    } catch (err) {
      if (!(err instanceof FlowTimeout)) throw err;
      return await fail("degraded", "amount form (#txtSendAmount) did not appear");
    }
    // Angular initialises the form after the limits call; a value typed before that is reset to 0.00.
    try {
      await page.waitForText("Enviar at[ée]", 15_000);
      trail.push("limits:ready");
    } catch (err) {
      if (!(err instanceof FlowTimeout)) throw err;
      trail.push("limits:not-seen");
    }
    try {
      await page.selectOption(SELECTORS.currency_select, "PYG", STEP_TIMEOUT_MS);
    } catch (err) {
      trail.push(`currency-select-skipped:${err instanceof Error ? err.name : "unknown"}`);
    }
    let amountOk = false;
    for (let attempt = 1; attempt <= 3; attempt++) {
      await page.fill(SELECTORS.send_amount, amount);
      await page.pressTab();
      try {
        // the value must survive AND the receive tiles must render for it
        await page.waitForFunction(
          AMOUNT_READY_SRC,
          { sel: SELECTORS.send_amount, want: amount, tile: SELECTORS.fundsout_any },
          15_000,
        );
        amountOk = true;
        trail.push(`amount=${amount}` + (attempt > 1 ? `(try ${attempt})` : ""));
        break;
      } catch (err) {
        if (!(err instanceof FlowTimeout)) throw err;
        trail.push(`amount-reset(try ${attempt})`);
      }
    }
    if (!amountOk) {
      return await fail("degraded", "amount did not stick / receive tiles never rendered (form reset by the SPA)");
    }
    // let Angular bind the tile handlers before clicking (a click on a freshly rendered tile is lost)
    await page.wait(2_500);

    // 3) receive method, then payment method
    if (!(await clickFirst(RECEIVE_TILES[receive], RECEIVE_LABELS[receive], "receive"))) {
      return await fail("degraded", `receive option for '${receive}' not found`);
    }
    // a click on a tile the SPA is still wiring is lost: re-click the receive tile up to twice if payment tiles stay hidden
    for (let attempt = 0; attempt < 3; attempt++) {
      try {
        await page.waitFor(SELECTORS.fundsin_any, 5_000);
        trail.push("payment-tiles:visible");
        break;
      } catch (err) {
        if (!(err instanceof FlowTimeout)) throw err;
        if (attempt < 2) await clickFirst(RECEIVE_TILES[receive], RECEIVE_LABELS[receive], "receive-again");
      }
    }
    if (!(await clickFirst(PAYMENT_TILES[payment], PAYMENT_LABELS[payment], "payment"))) {
      return await fail("degraded", `payment option for '${payment}' not offered`);
    }
    if (bank && !(await clickFirst([], [bank], "bank"))) {
      trail.push(`bank:${bank}:not-found`);
    }

    // 4) wait for the quote (receive amount populated), then read the summary
    try {
      await page.waitForFunction(RECEIVE_POPULATED_SRC, { sel: SELECTORS.receive_amount }, STEP_TIMEOUT_MS);
    } catch (err) {
      if (!(err instanceof FlowTimeout)) throw err;
      return await fail("degraded", "receive amount never populated (option not accepted or selector drift)");
    }
    const receiveText = await page.inputValue(SELECTORS.receive_amount);
    const bodyText = await page.bodyText();
    const received = parseDecimalText(receiveText);
    scenario.receive_amount_pyg = received;
    scenario.receive_amount_text = receiveText;
    Object.assign(scenario, extractSummary(bodyText));
    trail.push(`receive=${receiveText}`);
    shot = await page.screenshot();
    return { status: "ok", message: "quote read", trail, scenario, screenshot: shot };
  } catch (err) {
    if (err instanceof FlowTimeout) {
      return await fail("degraded", `timeout: ${err.message.slice(0, 160)}`);
    }
    const name = err instanceof Error ? err.name : "Error";
    const message = err instanceof Error ? err.message : String(err);
    return await fail("error", `${name}: ${message.slice(0, 200)}`);
  }
}
