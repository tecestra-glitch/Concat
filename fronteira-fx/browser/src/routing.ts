// Bloqueio de recursos que não fazem falta para ler a cotação. Economiza CPU e rede no Chromium.
// Não é disfarce: o user-agent é o do projeto, o site continua recebendo os scripts e as XHR dele, e só os
// domínios de analytics, anúncios e tag managers listados abaixo são cortados.

export const BLOCKED_RESOURCE_TYPES: ReadonlySet<string> = new Set(["image", "media", "font"]);

// Domínios de terceiros que só medem ou anunciam. Casamento por sufixo de host (ex.: "www.googletagmanager.com").
export const BLOCKED_HOST_SUFFIXES: readonly string[] = [
  "google-analytics.com",
  "googletagmanager.com",
  "analytics.google.com",
  "doubleclick.net",
  "googlesyndication.com",
  "googleadservices.com",
  "facebook.net",
  "facebook.com",
  "hotjar.com",
  "amplitude.com",
  "segment.io",
  "segment.com",
  "mixpanel.com",
  "newrelic.com",
  "nr-data.net",
  "criteo.com",
  "taboola.com",
  "outbrain.com",
  "adobedtm.com",
  "demdex.net",
  "omtrdc.net",
  "bing.com",
];

export type RouteDecision = "block" | "allow";

function hostMatches(host: string, suffixes: readonly string[]): boolean {
  return suffixes.some((s) => host === s || host.endsWith(`.${s}`));
}

export function routeDecision(url: string, resourceType: string): RouteDecision {
  if (BLOCKED_RESOURCE_TYPES.has(resourceType)) return "block";
  let host: string;
  try {
    host = new URL(url).hostname.toLowerCase();
  } catch {
    return "allow";
  }
  return host && hostMatches(host, BLOCKED_HOST_SUFFIXES) ? "block" : "allow";
}

export interface RouteCounters {
  blocked: number;
  allowed: number;
}

/** The subset of Playwright's BrowserContext that routing needs (kept small so tests can fake it). */
export interface RoutableContext {
  route(
    pattern: string,
    handler: (route: {
      request(): { url(): string; resourceType(): string };
      abort(): Promise<unknown>;
      continue(): Promise<unknown>;
    }) => Promise<unknown>,
  ): Promise<unknown>;
}

export async function installRouting(context: RoutableContext, counters: RouteCounters): Promise<void> {
  await context.route("**/*", async (route) => {
    const req = route.request();
    if (routeDecision(req.url(), req.resourceType()) === "block") {
      counters.blocked += 1;
      await route.abort();
    } else {
      counters.allowed += 1;
      await route.continue();
    }
  });
}
