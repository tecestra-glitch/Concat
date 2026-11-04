import { describe, expect, it } from "vitest";
import { installRouting, routeDecision, type RoutableContext } from "../src/routing.js";
import { Trail } from "../src/trail.js";

const SITE = "https://www.westernunion.com/wuconnect/prices/catalog";

describe("routeDecision: bloqueia só o que não serve para a cotação", () => {
  it.each([
    ["imagem do próprio site", "https://www.westernunion.com/img/flag.png", "image"],
    ["mídia", "https://www.westernunion.com/video.mp4", "media"],
    ["fonte", "https://www.westernunion.com/fonts/x.woff2", "font"],
    ["tag manager", "https://www.googletagmanager.com/gtm.js", "script"],
    ["analytics do Google", "https://www.google-analytics.com/collect", "xhr"],
    ["anúncios", "https://securepubads.g.doubleclick.net/tag", "script"],
    ["amplitude", "https://cdn.amplitude.com/libs/x.js", "script"],
    ["subdomínio de analytics", "https://stats.hotjar.com/x", "fetch"],
  ])("bloqueia %s", (_name, url, type) => {
    expect(routeDecision(url, type)).toBe("block");
  });

  it.each([
    ["script do próprio site", "https://www.westernunion.com/main.js", "script"],
    ["XHR do próprio site (cotação)", SITE, "xhr"],
    ["fetch do próprio site", SITE, "fetch"],
    ["folha de estilo", "https://www.westernunion.com/styles.css", "stylesheet"],
    ["documento", "https://www.westernunion.com/br/pt/web/send-money/start", "document"],
    ["banner de cookies", "https://cdn.cookielaw.org/consent.js", "script"],
    ["domínio que só termina parecido", "https://notgoogle-analytics.com.example/x.js", "script"],
    ["URL que não é válida", "not a url", "script"],
  ])("libera %s", (_name, url, type) => {
    expect(routeDecision(url, type)).toBe("allow");
  });
});

describe("installRouting", () => {
  it("aborta os bloqueados, continua os demais e conta cada decisão", async () => {
    let handler: ((route: unknown) => Promise<unknown>) | null = null;
    const ctx: RoutableContext = {
      route: async (_pattern, h) => {
        handler = h as unknown as (route: unknown) => Promise<unknown>;
      },
    };
    const counters = { blocked: 0, allowed: 0 };
    await installRouting(ctx, counters);
    const log: string[] = [];
    const fake = (url: string, type: string) => ({
      request: () => ({ url: () => url, resourceType: () => type }),
      abort: async () => void log.push("abort"),
      continue: async () => void log.push("continue"),
    });
    if (handler === null) throw new Error("routing não instalado");
    const h = handler as (route: unknown) => Promise<unknown>;
    await h(fake("https://www.westernunion.com/logo.png", "image"));
    await h(fake(SITE, "xhr"));
    await h(fake("https://www.googletagmanager.com/gtm.js", "script"));
    expect(log).toEqual(["abort", "continue", "abort"]);
    expect(counters).toEqual({ blocked: 2, allowed: 1 });
  });
});

describe("Trail: cada passo com o tempo desde o início", () => {
  it("formata segundos com uma casa decimal", () => {
    let ms = 41_200;
    const trail = new Trail(() => ms);
    trail.add("amount=5000");
    ms = 110_049;
    trail.add("receive=5401871.00");
    expect(trail.steps).toEqual(["amount=5000@41.2s", "receive=5401871.00@110.0s"]);
    expect(trail.labels()).toEqual(["amount=5000", "receive=5401871.00"]);
  });

  it("nunca mostra tempo negativo", () => {
    const trail = new Trail(() => -50);
    trail.add("goto=200");
    expect(trail.steps).toEqual(["goto=200@0.0s"]);
  });
});
