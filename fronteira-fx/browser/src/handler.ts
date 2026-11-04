import { bearerMatches, usableSecret } from "./auth.js";
import { runWesternUnionFlow, type FlowResult, type FlowStatus } from "./flow.js";
import { openWesternUnionPage, type OpenedPage } from "./playwright-page.js";
import { WesternUnionRequest } from "./request.js";

// The Vercel function has maxDuration 120 s; the flow gets a little less so the response always goes out.
export const FLOW_BUDGET_MS = 110_000;

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

function deadline(ms: number, trail: string[]): Promise<FlowResult> {
  return new Promise((resolve) => {
    setTimeout(() => {
      resolve({
        status: "degraded",
        message: `deadline de ${Math.round(ms / 1000)} s atingido; steps: ${trail.join(" > ")}`,
        trail: [...trail],
        scenario: null,
        screenshot: null,
      });
    }, ms).unref();
  });
}

function bytesToBase64(bytes: Uint8Array): string {
  return Buffer.from(bytes).toString("base64");
}

/**
 * POST /api/westernunion. Pure with respect to the request: `env` carries BROWSER_SECRET (and the optional local
 * CHROMIUM_EXECUTABLE_PATH). The response carries only the status, the message, the trail, the scenario and, when
 * asked, the screenshot. It never carries cookies, headers or session data.
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

  const trail: string[] = [];
  let result: FlowResult;
  try {
    result = await Promise.race([
      runWesternUnionFlow(opened.page, input, deps.now(), { trail }),
      deadline(deps.budgetMs, trail),
    ]);
  } finally {
    await opened.close();
  }

  const body: Record<string, unknown> = {
    status: result.status,
    message: result.message,
    trail: result.trail,
    scenario: result.scenario,
  };
  if (input.screenshot && result.screenshot) {
    body.screenshot_png_b64 = bytesToBase64(result.screenshot);
  }
  return { status: 200, body };
}
