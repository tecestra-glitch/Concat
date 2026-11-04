// A simulated Western Union page: a few flags describe what the SPA shows, and the FlowPage operations read and change
// that state. No browser, no network. Predicates (source strings) are evaluated against a fake `document`.
import {
  FlowTimeout,
  PAYMENT_TILES,
  RECEIVE_TILES,
  SELECTORS,
  type FlowPage,
} from "../src/flow.js";

// Visible page text captured live on 2026-11-02 (same text as the backend test suite).
export const LIVE_BODY =
  "Valor a enviar\nBRL\nValor a receber\nPYG\nUSD\nEnviar até 25,000.00 BRL\n\n1.00 BRL = 1,080.3741 Paraguay Guarani " +
  "(PYG) 2\n\nComo o seu destinatário quer receber o dinheiro?\nReceber em dinheiro\nem uma loja\nConta Bancaria10\n" +
  "Como você gostaria de pagar?\nPIX ou transferência bancária4\n0-4 Dias úteis1, 8, 12\nTarifa2 0.00  BRL\n\n" +
  "Tenho um código promocional\nContinuar\nRESUMO\nTAXA DE CÂMBIO2\n1.00 BRL = 1,080.3741 PYG\nValor da transferência\n" +
  "5,000.00 BRL\n100% de desconto 45.00 BRL\nTaxa de transferência2\n+ 0.00 BRL\nTotal da transferência\n5,000.00 BRL\n" +
  "Total  O destinatário recebe\n5,401,871.00PYG\nTempo de atendimento:1, 8, 12\n0-4 Dias úteis\n0 to 4 Dia";

export interface FakeOptions {
  /** HTTP status of the start page (default 200). */
  status?: number | null;
  /** The "Paraguai" country tile is shown (default true). */
  countryTile?: boolean;
  /** Visible body text (default LIVE_BODY). */
  body?: string;
  /** The "Enviar até" limits text appears (default true). */
  limits?: boolean;
  /** The SPA keeps the typed amount (default true); false resets it to 0.00 on Tab. */
  amountSticks?: boolean;
  /** The receive tiles (bank / cash) are offered (default true). */
  receiveOffered?: boolean;
  /** The payment tiles appear after a receive click (default true). */
  paymentOffered?: boolean;
  /** Clicking the payment tile fills the receive amount (default true). */
  quoteAppears?: boolean;
  /** The receive amount text shown once the quote appears (default "5,401,871.00"). */
  receiveText?: string;
  /** Every wait never resolves (simulates a hung page). */
  hang?: boolean;
}

const SEND = SELECTORS.send_amount;
const RECV = SELECTORS.receive_amount;
const PIX_TILES = PAYMENT_TILES.pix;

export class FakeWuPage implements FlowPage {
  readonly values = new Map<string, string>([
    [SEND, ""],
    [RECV, "0.00"],
  ]);
  readonly calls: string[] = [];
  private clickedCountry = false;
  private selectedReceive = false;
  private selectedPayment = false;

  constructor(readonly o: FakeOptions = {}) {}

  private hangIfAsked(): Promise<never> | null {
    return this.o.hang ? new Promise<never>(() => undefined) : null;
  }

  private amountAccepted(): boolean {
    return this.o.amountSticks !== false;
  }

  private fundsoutVisible(): boolean {
    return this.clickedCountry && this.amountAccepted();
  }

  private isReceiveTile(sel: string): boolean {
    return RECEIVE_TILES.bank_account.includes(sel) || RECEIVE_TILES.cash_pickup.includes(sel);
  }

  private isPaymentTile(sel: string): boolean {
    return sel.includes("tile-fundsin") || sel.startsWith("#fundsIn") || PIX_TILES.includes(sel);
  }

  async goto(): Promise<number | null> {
    this.calls.push("goto");
    const hung = this.hangIfAsked();
    if (hung) return hung;
    return this.o.status === undefined ? 200 : this.o.status;
  }

  async waitFor(selector: string, _timeoutMs: number, hasText?: string): Promise<void> {
    this.calls.push(`waitFor:${selector}`);
    const hung = this.hangIfAsked();
    if (hung) return hung;
    if (selector === SELECTORS.country_tile) {
      if (this.o.countryTile !== false && hasText === "Paraguai") return;
      throw new FlowTimeout("country tile");
    }
    if (selector === SEND) return;
    if (this.isReceiveTile(selector)) {
      if (this.o.receiveOffered !== false) return;
      throw new FlowTimeout("receive tile");
    }
    if (this.isPaymentTile(selector)) {
      if (this.selectedReceive && this.o.paymentOffered !== false) return;
      throw new FlowTimeout("payment tiles");
    }
    throw new FlowTimeout(`no ${selector}`);
  }

  async click(selector: string, _timeoutMs: number, hasText?: string): Promise<void> {
    this.calls.push(`click:${selector}`);
    const hung = this.hangIfAsked();
    if (hung) return hung;
    if (selector === SELECTORS.country_tile && hasText === "Paraguai") {
      this.clickedCountry = true;
      return;
    }
    if (this.isReceiveTile(selector)) {
      if (this.o.receiveOffered === false) throw new FlowTimeout("receive tile");
      this.selectedReceive = true;
      return;
    }
    if (this.isPaymentTile(selector)) {
      if (!this.selectedReceive || this.o.paymentOffered === false) throw new FlowTimeout("payment tile");
      this.selectedPayment = true;
      if (this.o.quoteAppears !== false) {
        this.values.set(RECV, this.o.receiveText ?? "5,401,871.00");
      }
      return;
    }
    throw new FlowTimeout(`not clickable ${selector}`);
  }

  async clickByText(label: string): Promise<void> {
    this.calls.push(`clickByText:${label}`);
    throw new FlowTimeout(`no text ${label}`);
  }

  async waitForText(pattern: string): Promise<void> {
    this.calls.push(`waitForText:${pattern}`);
    const hung = this.hangIfAsked();
    if (hung) return hung;
    if (pattern.startsWith("Enviar") && this.o.limits !== false) return;
    throw new FlowTimeout("no text");
  }

  async fill(selector: string, value: string): Promise<void> {
    this.calls.push(`fill:${selector}=${value}`);
    this.values.set(selector, value);
  }

  async pressTab(): Promise<void> {
    this.calls.push("Tab");
    if (!this.amountAccepted()) this.values.set(SEND, "0.00");
  }

  async selectOption(selector: string, value: string): Promise<void> {
    this.calls.push(`select:${selector}=${value}`);
  }

  async waitForFunction(source: string, arg: unknown, _timeoutMs: number): Promise<void> {
    this.calls.push("waitForFunction");
    const hung = this.hangIfAsked();
    if (hung) return hung;
    const predicate = new Function(`return (${source});`)() as (a: unknown) => boolean;
    const doc = {
      querySelector: (selector: string): { value?: string } | null => {
        if (selector === SEND || selector === RECV) return { value: this.values.get(selector) ?? "" };
        if (selector === SELECTORS.fundsout_any) return this.fundsoutVisible() ? {} : null;
        return null;
      },
    };
    const g = globalThis as unknown as { document?: unknown };
    const previous = g.document;
    g.document = doc;
    let ok = false;
    try {
      ok = predicate(arg);
    } finally {
      g.document = previous;
    }
    if (!ok) throw new FlowTimeout("predicate false");
  }

  async inputValue(selector: string): Promise<string> {
    return this.values.get(selector) ?? "";
  }

  async bodyText(): Promise<string> {
    return this.o.body ?? LIVE_BODY;
  }

  async screenshot(): Promise<Uint8Array> {
    this.calls.push("screenshot");
    return new Uint8Array([0x89, 0x50, 0x4e, 0x47]);
  }

  async wait(): Promise<void> {
    this.calls.push("wait");
  }
}
