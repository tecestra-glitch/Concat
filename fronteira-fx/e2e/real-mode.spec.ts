import { expect, test, type Page, type Route } from "@playwright/test";

/**
 * Modo real com a API simulada por `page.route` em `/api/fx/**` (o proxy D5 nunca é alcançado).
 * Cobre: faixa de demonstração ausente, health real, cotações reais, 401 em mutação, 500 com
 * «Tentar de novo», 410 do stream → novo snapshot e reconexão sem cursor, cidade «digital» não
 * enviada como `city`, busca de conhecimento e memória. Nunca `networkidle`.
 */
const NOW = Date.now();
const iso = (secondsAgo: number) => new Date(NOW - secondsAgo * 1000).toISOString();

const SOURCES = [
  { id: "chaco", name: "Cambios Chaco", kind: "exchange_house", method: "html", url: "https://www.cambioschaco.com.py/", health: "ok", last_success_at: iso(120), last_error: null, capabilities: ["buy_sell"], limitations: [], coverage: { cities: ["CDE"], currencies: ["USD", "BRL", "PYG"] }, poll_interval_s: 300, data_mode: "real" },
  { id: "bcp", name: "BCP", kind: "central_bank", method: "html", url: "https://www.bcp.gov.py/", health: "ok", last_success_at: iso(900), last_error: null, capabilities: ["market_reference"], limitations: ["referência"], coverage: { cities: [], currencies: ["USD", "PYG"] }, poll_interval_s: 3600, data_mode: "real" },
];

function quote(id: string, patch: Record<string, unknown>) {
  return {
    id, series_key: `chaco:CDE:USD/PYG:cash:@chaco-cde`, source_id: "chaco", branch_id: "chaco-cde", city: "CDE", base: "USD", quote: "PYG", buy: "7320", sell: "7390", unit_note: "PYG por 1 USD",
    amount_base: null, modality: "cash", kind: "indicative", channel: "physical", context: null, fees: [], captured_at: iso(60), declared_updated_at: null, valid_until: null, evidence_id: "ev-1", data_mode: "real", ...patch,
  };
}
const QUOTES = [
  quote("q-1", {}),
  quote("q-2", { series_key: "chaco:CDE:BRL/PYG:cash:@chaco-cde", base: "BRL", buy: "1340", sell: "1365", unit_note: "PYG por 1 BRL" }),
  quote("q-ref", { series_key: "bcp:digital:USD/PYG:transfer", source_id: "bcp", branch_id: null, city: null, buy: "7355.12", sell: "7355.12", modality: "transfer", kind: "market_reference", channel: "digital", captured_at: iso(900) }),
];
const HEALTH = { status: "ok", data_mode: "real", version: "0.1.0", server_time: new Date(NOW).toISOString() };
const snapshotAt = (n: number) => ({ cursor: `evt-${10 * n}`, server_time: new Date(NOW).toISOString(), quotes: QUOTES, sources: SOURCES, opportunities: [], data_mode: "real" });

type Overrides = Record<string, (route: Route, url: URL) => Promise<void> | void>;
interface Log { streams: URL[]; snapshots: number; quotes: URL[]; rag: URL[] }

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

/** Switches the app to real mode (or `preference`) and installs the fake API. */
async function setupRealMode(page: Page, overrides: Overrides = {}, preference = "real"): Promise<Log> {
  const log: Log = { streams: [], snapshots: 0, quotes: [], rag: [] };
  await page.addInitScript((pref) => localStorage.setItem("fronteira-fx.settings.v1", JSON.stringify({ modePreference: pref, defaultCapital: 5000, valuationCurrency: "BRL", pollFallbackSeconds: 30 })), preference);
  await page.route("**/api/fx/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname.replace(/^.*\/api\/fx/, "");
    const method = route.request().method();
    const key = `${method} ${path}`;
    const override = overrides[key] ?? overrides[path];
    if (override) return override(route, url);
    switch (path) {
      case "/v1/health": return json(route, HEALTH);
      case "/v1/sources": return json(route, SOURCES);
      case "/v1/quotes": log.quotes.push(url); return json(route, QUOTES);
      case "/v1/snapshot": log.snapshots += 1; return json(route, snapshotAt(log.snapshots));
      case "/v1/stream": {
        log.streams.push(url);
        if (log.streams.length === 1) return json(route, { detail: "cursor expirado" }, 410);
        const ts = new Date().toISOString();
        return route.fulfill({ status: 200, contentType: "text/event-stream", body: `id: evt-${10 + log.streams.length}\ndata: ${JSON.stringify({ id: `evt-${10 + log.streams.length}`, type: "heartbeat", ts, payload: {} })}\n\n` });
      }
      case "/v1/opportunities": return json(route, []);
      case "/v1/opportunities/cycles": return json(route, []);
      case "/v1/history": return json(route, { key: url.searchParams.get("key"), points: [] });
      case "/v1/accounts": return method === "POST" ? json(route, { detail: "chave de API inválida" }, 401) : json(route, []);
      case "/v1/journal": return json(route, []);
      case "/v1/evidence": return json(route, []);
      case "/v1/watch/sources": return json(route, []);
      case "/v1/watch/changes": return json(route, []);
      case "/v1/alerts/rules": return json(route, []);
      case "/v1/alerts/events": return json(route, []);
      case "/v1/memory/summary": return json(route, { summary: "Prefere ciclos digitais; evitar presencial em PJC." });
      case "/v1/memory": return json(route, [{ id: "m1", kind: "decision", text: "Não operar com cotação acima de 30 min.", tags: ["regra"], created_at: iso(3600), expires_at: null, source: "user" }]);
      case "/v1/rag/search": log.rag.push(url); return json(route, [{ id: "h1", document_id: "d1", title: "Tarifas ueno", snippet: "Saque em caixa: 0,5 %…", score: 0.82, source: "ueno", tags: ["tarifa"] }]);
      default: return json(route, { detail: `sem rota simulada para ${path}` }, 404);
    }
  });
  return log;
}

test.describe("Modo real (API simulada)", () => {
  test("hides the demo banner, shows real health and quotes from the backend", async ({ page }) => {
    await setupRealMode(page);
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 2, name: "Visão geral" })).toBeVisible();
    await expect(page.getByTestId("price-card-USDPYG")).toContainText("Cambios Chaco");
    await expect(page.getByTestId("price-card-USDPYG")).toContainText("7.320");
    await expect(page.getByTestId("demo-banner")).toHaveCount(0);
    await expect(page.getByTestId("connection-status")).not.toHaveAttribute("data-state", "demo");
    await page.goto("/configuracoes");
    await expect(page.getByTestId("backend-status")).toHaveText("disponível");
    await expect(page.getByTestId("effective-mode")).toHaveText("real");
    await expect(page.getByText("ok · real · v0.1.0")).toBeVisible();
  });

  test("«Simulação» against a real backend is a conflict: never labelled simulation, calls refused", async ({ page }) => {
    const declared: (string | null)[] = [];
    await setupRealMode(page, {
      "/v1/accounts": (route, url) => {
        declared.push(url.searchParams.get("data_mode"));
        return json(route, { detail: "esta instância serve data_mode=real; o pedido declarou data_mode=simulation." }, 409);
      },
    }, "simulation");
    await page.goto("/contas");
    await expect(page.getByTestId("mode-conflict-banner")).toContainText("Real");
    await expect(page.getByTestId("simulation-banner")).toHaveCount(0);
    await expect.poll(() => declared.length).toBeGreaterThan(0);
    expect(declared.every((m) => m === "simulation")).toBe(true);
    await page.goto("/configuracoes");
    await expect(page.getByTestId("mode-conflict")).toContainText("recusadas");
  });

  test("«Automático» follows a simulation instance and labels it", async ({ page }) => {
    await setupRealMode(page, { "/v1/health": (route) => json(route, { ...HEALTH, data_mode: "simulation" }) }, "auto");
    await page.goto("/configuracoes");
    await expect(page.getByTestId("effective-mode")).toHaveText("simulação");
    await expect(page.getByTestId("simulation-banner")).toBeVisible();
    await expect(page.getByTestId("mode-conflict-banner")).toHaveCount(0);
  });

  test("410 on the stream drops the stale cursor, takes a fresh snapshot and resumes from its cursor", async ({ page }) => {
    const log = await setupRealMode(page);
    await page.goto("/");
    await expect.poll(() => log.streams.length, { timeout: 20_000 }).toBeGreaterThanOrEqual(2);
    // 1st stream: cursor of the 1st snapshot → 410. 2nd stream: never the stale cursor; it carries the 2nd snapshot's.
    expect(log.streams[0].searchParams.get("cursor")).toBe("evt-10");
    expect(log.snapshots).toBeGreaterThanOrEqual(2);
    expect(log.streams[1].searchParams.get("cursor")).not.toBe("evt-10");
    expect(log.streams[1].searchParams.get("cursor")).toBe("evt-20");
  });

  test("401 on a mutation is shown inside the dialog and keeps what was typed", async ({ page }) => {
    await setupRealMode(page);
    await page.goto("/contas");
    await page.getByRole("button", { name: "Cadastrar conta" }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByLabel("Instituição").fill("Banco Real");
    await dialog.getByLabel("Rótulo").fill("Conta 401");
    await dialog.getByRole("button", { name: "Salvar" }).click();
    await expect(dialog.getByTestId("account-error")).toContainText("401");
    await expect(dialog.getByTestId("account-error")).toContainText("chave de API inválida");
    await expect(dialog).toBeVisible();
    await expect(dialog.getByLabel("Rótulo")).toHaveValue("Conta 401");
  });

  test("500 on quotes shows an error state whose retry recovers", async ({ page }) => {
    let fail = true;
    // While the backend is down the snapshot fails too (otherwise the live layer fills the quotes cache from it).
    await setupRealMode(page, {
      "/v1/quotes": (route) => (fail ? json(route, { detail: "banco indisponível" }, 500) : json(route, QUOTES)),
      "/v1/snapshot": (route) => (fail ? json(route, { detail: "banco indisponível" }, 500) : json(route, snapshotAt(1))),
    });
    await page.goto("/mercados");
    const alert = page.getByRole("alert").filter({ hasText: "As cotações não carregaram" }).first();
    await expect(alert).toBeVisible();
    await expect(alert).toContainText("Tentar de novo");
    fail = false;
    await alert.getByRole("button", { name: "Tentar de novo" }).click();
    await expect(page.getByRole("region", { name: /Tabela de cotações/ }).first()).toBeVisible();
    await expect(page.getByText("Cambios Chaco").first()).toBeVisible();
  });

  test("«Digital (sem cidade)» never travels as city=digital", async ({ page }) => {
    const log = await setupRealMode(page);
    await page.goto("/mercados");
    await expect(page.getByText("Cambios Chaco").first()).toBeVisible();
    await page.getByLabel("Cidade").first().click();
    await page.getByRole("option", { name: "Digital (sem cidade)" }).click();
    await expect.poll(() => log.quotes.length).toBeGreaterThanOrEqual(2);
    for (const u of log.quotes) expect(u.searchParams.get("city")).not.toBe("digital");
  });

  test("knowledge search calls /v1/rag/search and lists hits", async ({ page }) => {
    const log = await setupRealMode(page);
    await page.goto("/conhecimento");
    await page.getByLabel("Pergunta ou termo").fill("tarifa ueno");
    await page.getByRole("button", { name: "Buscar" }).click();
    await expect(page.getByTestId("knowledge-results")).toContainText("Tarifas ueno");
    expect(log.rag[0].searchParams.get("q")).toBe("tarifa ueno");
    expect(log.rag[0].searchParams.get("k")).toBe("5");
  });

  test("memory shows the summary and the list from the backend", async ({ page }) => {
    await setupRealMode(page);
    await page.goto("/memoria");
    await expect(page.getByTestId("memory-summary")).toContainText("Prefere ciclos digitais");
    await expect(page.getByTestId("memory-list")).toContainText("Não operar com cotação acima de 30 min.");
    await expect(page.getByTestId("memory-list")).toContainText("Decisão");
  });
});
