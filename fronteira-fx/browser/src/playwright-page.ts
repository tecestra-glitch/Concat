import Chromium from "@sparticuz/chromium";
import { chromium, type Browser, type Page, type Response } from "playwright-core";
import { catalogAmount, isCatalogUrl, sameAmount } from "./catalog.js";
import { escapeRegExp, FlowTimeout, type FlowPage } from "./flow.js";
import { installRouting, type RouteCounters } from "./routing.js";

// Same user agent as the backend's adapters (adapters/_http.py). Not a stealth setup: no fingerprint changes.
export const USER_AGENT =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36";

function isTimeout(err: unknown): boolean {
  return err instanceof Error && err.name === "TimeoutError";
}

/** Runs one Playwright call and turns its timeouts into FlowTimeout, the only error the flow treats as "not there". */
async function guard<T>(op: () => Promise<T>): Promise<T> {
  try {
    return await op();
  } catch (err) {
    if (isTimeout(err)) throw new FlowTimeout(err instanceof Error ? err.message.split("\n")[0] : "timeout");
    throw err;
  }
}

interface CapturedCatalog {
  amount: string | null;
  body: unknown;
}

export class PlaywrightFlowPage implements FlowPage {
  private readonly catalogs: CapturedCatalog[] = [];
  private readonly waiters = new Set<() => void>();

  constructor(private readonly page: Page) {
    // Keeps the parsed JSON of the site's own price responses in memory only (never logged, never returned as is).
    page.on("response", (resp) => {
      void this.onResponse(resp).catch(() => undefined);
    });
  }

  private async onResponse(resp: Response): Promise<void> {
    if (!isCatalogUrl(resp.url())) return;
    const req = resp.request();
    if (req.method() !== "POST" || !resp.ok()) return;
    const contentType = resp.headers()["content-type"] ?? "";
    if (!contentType.includes("json")) return;
    const body: unknown = await resp.json();
    this.catalogs.push({ amount: catalogAmount(req.postData()), body });
    for (const wake of [...this.waiters]) wake();
  }

  goto(url: string, timeoutMs: number): Promise<number | null> {
    return guard(async () => {
      const resp = await this.page.goto(url, { waitUntil: "domcontentloaded", timeout: timeoutMs });
      return resp ? resp.status() : null;
    });
  }

  waitFor(selector: string, timeoutMs: number, hasText?: string): Promise<void> {
    return guard(() =>
      this.page.locator(selector, hasText ? { hasText } : undefined).first().waitFor({ timeout: timeoutMs }),
    );
  }

  click(selector: string, timeoutMs: number, hasText?: string): Promise<void> {
    return guard(() =>
      this.page.locator(selector, hasText ? { hasText } : undefined).first().click({ timeout: timeoutMs }),
    );
  }

  clickByText(label: string, timeoutMs: number): Promise<void> {
    return guard(async () => {
      const loc = this.page.getByText(new RegExp(escapeRegExp(label), "i")).first();
      await loc.waitFor({ timeout: timeoutMs });
      await loc.click();
    });
  }

  waitForText(pattern: string, timeoutMs: number): Promise<void> {
    return guard(() =>
      this.page.getByText(new RegExp(pattern, "i")).first().waitFor({ timeout: timeoutMs }),
    );
  }

  fill(selector: string, value: string): Promise<void> {
    return guard(() => this.page.fill(selector, value));
  }

  pressTab(): Promise<void> {
    return guard(() => this.page.keyboard.press("Tab"));
  }

  selectOption(selector: string, value: string, timeoutMs: number): Promise<void> {
    return guard(async () => {
      await this.page.selectOption(selector, value, { timeout: timeoutMs });
    });
  }

  waitForFunction(source: string, arg: unknown, timeoutMs: number): Promise<void> {
    return guard(async () => {
      await this.page.waitForFunction(source, arg, { timeout: timeoutMs });
    });
  }

  inputValue(selector: string): Promise<string> {
    return guard(() => this.page.inputValue(selector));
  }

  bodyText(): Promise<string> {
    return guard(() => this.page.innerText("body"));
  }

  async screenshot(): Promise<Uint8Array> {
    // bounded: a screenshot taken of a page that never loaded must not eat the whole budget
    return guard(async () => new Uint8Array(await this.page.screenshot({ fullPage: true, type: "png", timeout: 15_000 })));
  }

  wait(ms: number): Promise<void> {
    return guard(() => this.page.waitForTimeout(ms));
  }

  url(): string {
    return this.page.url();
  }

  async title(): Promise<string | null> {
    try {
      return await this.page.title();
    } catch {
      return null;
    }
  }

  async waitForCatalog(amount: string, timeoutMs: number): Promise<unknown | null> {
    const deadline = Date.now() + timeoutMs;
    for (;;) {
      for (let i = this.catalogs.length - 1; i >= 0; i--) {
        const hit = this.catalogs[i] as CapturedCatalog;
        if (hit.amount !== null && sameAmount(hit.amount, amount)) return hit.body;
      }
      const left = deadline - Date.now();
      if (left <= 0) return null;
      await new Promise<void>((resolve) => {
        const wake = (): void => {
          clearTimeout(timer);
          this.waiters.delete(wake);
          resolve();
        };
        const timer = setTimeout(wake, left);
        this.waiters.add(wake);
      });
    }
  }
}

export interface OpenedPage {
  page: FlowPage;
  /** Counts of requests blocked and allowed by routing (no URLs, no headers). */
  counters: RouteCounters;
  close(): Promise<void>;
}

/**
 * Starts a headless Chromium and a page with the backend's locale, user agent and viewport.
 * - `CHROMIUM_EXECUTABLE_PATH` set (local tests): launch that binary.
 * - otherwise (Vercel): the Chromium that `@sparticuz/chromium` inflates into /tmp, with its serverless flags.
 * Images, media, fonts and the analytics/ads domains of routing.ts are blocked; the site's own scripts and XHR load.
 */
export async function openWesternUnionPage(env: Record<string, string | undefined>): Promise<OpenedPage> {
  const localPath = env.CHROMIUM_EXECUTABLE_PATH?.trim();
  let browser: Browser;
  if (localPath) {
    browser = await chromium.launch({ executablePath: localPath, headless: true });
  } else {
    // sparticuz passes `--headless='shell'` itself; Playwright adds its own headless switch, so drop the duplicate.
    const args = Chromium.args.filter((a) => !a.startsWith("--headless"));
    browser = await chromium.launch({ executablePath: await Chromium.executablePath(), headless: true, args });
  }
  try {
    const context = await browser.newContext({
      locale: "pt-BR",
      userAgent: USER_AGENT,
      viewport: { width: 1280, height: 2400 },
    });
    const counters: RouteCounters = { blocked: 0, allowed: 0 };
    await installRouting(context, counters);
    const page = await context.newPage();
    return {
      page: new PlaywrightFlowPage(page),
      counters,
      close: () => browser.close().catch(() => undefined),
    };
  } catch (err) {
    await browser.close().catch(() => undefined);
    throw err;
  }
}
