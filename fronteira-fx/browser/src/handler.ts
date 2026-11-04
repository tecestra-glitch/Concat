import { bearerMatches, usableSecret } from "./auth.js";
import { runWesternUnionFlow, type FlowPage, type FlowResult, type FlowStatus } from "./flow.js";
import { openWesternUnionPage, type OpenedPage } from "./playwright-page.js";
import { WesternUnionRequest } from "./request.js";
import { startedClock, Trail } from "./trail.js";

// The Vercel function has maxDuration 120 s. The flow gets 110 s, and what is left covers the capture at the
// deadline (bounded) and closing the browser, so the response always goes out inside 120 s.
export const FLOW_BUDGET_MS = 110_000;
/** Ceiling for FLOW_BUDGET_MS: 120 s of maxDuration minus the capture and close margins. */
export const MAX_FLOW_BUDGET_MS = 115_000;
/** Each capture at the deadline (title and screenshot, in parallel) is cut at this time. */
export const CAPTURE_TIMEOUT_MS = 5_000;
const CLOSE_TIMEOUT_MS = 3_000;

export interface HandlerRequest {
  method?: string | undefined;
  authorization?: string | undefined;
  body: unknown;
}

export interface HandlerResponse {
  status: number;
  headers?: Record<string, string>;
  body: Record<string, unknown>;
}

export interface HandlerDeps {
  open: (env: Record<string, string | undefined>) => Promise<OpenedPage>;
  now: () => Date;
  budgetMs: number;
}

export const defaultDeps: HandlerDeps = {
  open: openWesternUnionPage,
  now: () => new Date(),
  budgetMs: FLOW_BUDGET_MS,
};

/** FLOW_BUDGET_MS from the environment, clamped to [5 s, MAX_FLOW_BUDGET_MS]; null when unset or not a number. */
export function budgetFromEnv(raw: string | undefined): number | null {
  if (raw === undefined || raw.trim() === "") return null;
  const n = Number(raw);
  if (!Number.isFinite(n) || n <= 0) return null;
  return Math.min(Math.max(Math.round(n), 5_000), MAX_FLOW_BUDGET_MS);
}

/** Only origin and path: the query string can carry session identifiers, so it is never reported. */
export function safeUrl(url: string): string {
  try {
    const u = new URL(url);
    return `${u.origin}${u.pathname}`;
  } catch {
    return "";
  }
}

/** Resolves with `null` after `ms`, or with the value (or null on error) if `p` settles first. */
function bounded<T>(p: Promise<T>, ms: number): Promise<T | null> {
  return new Promise((resolve) => {
    const timer = setTimeout(() => resolve(null), ms);
    p.then(
      (v) => {
        clearTimeout(timer);
        resolve(v);
      },
      () => {
        clearTimeout(timer);
        resolve(null);
      },
    );
  });
}

/** Reads the page at the deadline: URL (without query), title and, if asked, a screenshot. Never cookies or headers. */
export async function captureAtDeadline(
  page: FlowPage,
  withScreenshot: boolean,
  ms: number = CAPTURE_TIMEOUT_MS,
): Promise<{ url: string; title: string | null; screenshot: Uint8Array | null }> {
  let url = "";
  try {
    url = safeUrl(page.url());
  } catch {
    url = "";
  }
  const [title, screenshot] = await Promise.all([
    bounded(page.title(), ms),
    withScreenshot ? bounded(page.screenshot(), ms) : Promise.resolve(null),
  ]);
  return { url, title: title ?? null, screenshot: screenshot ?? null };
}

function bytesToBase64(bytes: Uint8Array): string {
  return Buffer.from(bytes).toString("base64");
}

/**
 * POST /api/westernunion. Pure with respect to the request: `env` carries BROWSER_SECRET (and the optional local
 * CHROMIUM_EXECUTABLE_PATH and FLOW_BUDGET_MS). The response carries only the status, the message, the trail (with
 * the time of each step), the scenario and, when asked, the screenshot. It never carries cookies, headers or session data.
 */
export async function handleWesternUnion(
  req: HandlerRequest,
  env: Record<string, string | undefined>,
  deps: HandlerDeps = defaultDeps,
): Promise<HandlerResponse> {
  const secret = usableSecret(env.BROWSER_SECRET);
  if (!secret) return { status: 404, body: { error: "not_found" } };
  if (req.method !== "POST") {
    return { status: 405, headers: { Allow: "POST" }, body: { error: "method_not_allowed" } };
  }
  if (!bearerMatches(req.authorization, secret)) {
    return { status: 401, body: { error: "unauthorized" } };
  }

  const parsed = WesternUnionRequest.safeParse(req.body);
  if (!parsed.success) {
    return {
      status: 400,
      body: {
        status: "error",
        error: "invalid_request",
        issues: parsed.error.issues.map((i) => ({ path: i.path.join("."), message: i.message })),
      },
    };
  }
  const input = parsed.data;
  const wantShot = input.screenshot === true;
  const budgetMs = budgetFromEnv(env.FLOW_BUDGET_MS) ?? deps.budgetMs;
  const trail = new Trail(startedClock());

  let opened: OpenedPage;
  try {
    opened = await deps.open(env);
  } catch (err) {
    const name = err instanceof Error ? err.name : "Error";
    return {
      status: 200,
      body: { status: "error" satisfies FlowStatus, message: `chromium não iniciou (${name})`, trail: [], scenario: null },
    };
  }

  let result: FlowResult;
  let pageAtDeadline: { url: string; title: string | null } | null = null;
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    const flow = runWesternUnionFlow(opened.page, input, deps.now(), { trail, screenshot: wantShot }).catch(
      (err: unknown): FlowResult => ({
        status: "error",
        message: `erro inesperado: ${err instanceof Error ? err.name : "Error"}`,
        trail: [...trail.steps],
        scenario: null,
        screenshot: null,
        source: null,
      }),
    );
    const deadline = new Promise<null>((resolve) => {
      timer = setTimeout(() => resolve(null), budgetMs);
    });
    const outcome = await Promise.race([flow, deadline]);
    if (outcome === null) {
      // The flow is still running: read the page now, while the browser is open, then the caller closes it.
      const snap = await captureAtDeadline(opened.page, wantShot);
      pageAtDeadline = { url: snap.url, title: snap.title };
      result = {
        status: "degraded",
        message: `deadline de ${Math.round(budgetMs / 1000)} s atingido; steps: ${trail.steps.join(" > ")}`,
        trail: [...trail.steps],
        scenario: null,
        screenshot: snap.screenshot,
        source: null,
      };
    } else {
      result = outcome;
    }
  } finally {
    if (timer !== undefined) clearTimeout(timer);
    await Promise.race([opened.close(), new Promise((r) => setTimeout(r, CLOSE_TIMEOUT_MS).unref())]);
  }

  const body: Record<string, unknown> = {
    status: result.status,
    message: result.message,
    trail: result.trail,
    scenario: result.scenario,
    source: result.source,
    routing: { blocked: opened.counters.blocked, allowed: opened.counters.allowed },
  };
  if (pageAtDeadline) body.page = pageAtDeadline;
  if (wantShot && result.screenshot) {
    body.screenshot_png_b64 = bytesToBase64(result.screenshot);
  }
  return { status: 200, body };
}
