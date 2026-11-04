import { expect, test, type Page } from "@playwright/test";
import { ROUTES } from "./routes";

// Never rely on networkidle: the app keeps a live stream open.
async function expectNoHorizontalScroll(page: Page) {
  const scrollW = await page.evaluate(() => document.documentElement.scrollWidth);
  const clientW = await page.evaluate(() => document.documentElement.clientWidth);
  expect(scrollW).toBeLessThanOrEqual(clientW + 1);
}

test.describe("Fronteira FX terminal", () => {
  test("home shows candles and the top opportunities, without horizontal scroll", async ({ page }, info) => {
    await page.goto("/");
    await expect(page.getByTestId("demo-banner")).toBeVisible();
    await expect(page.getByRole("heading", { level: 1, name: "Início" })).toBeVisible();
    await expect(page.getByTestId("home-chart")).toHaveAttribute("data-state", "ready", { timeout: 15_000 });
    await expect(page.getByTestId("home-opportunities")).toBeVisible();
    // A home não repete as cotações por par nem o estado das fontes (saíram da home; vivem em Mercados e Fontes).
    await expect(page.getByTestId("price-card-USDPYG")).toHaveCount(0);
    await expect(page.getByTestId("sources-status")).toHaveCount(0);
    const rows = page.locator('[data-testid="home-opportunity-featured"], [data-testid="home-opportunity"]');
    expect(await rows.count()).toBeGreaterThanOrEqual(3);
    await expectNoHorizontalScroll(page);
    if (info.project.name === "mobile-390") {
      // No celular o gráfico vem antes da lista (ordem da tela, spec §5a).
      const chart = await page.getByTestId("home-chart").boundingBox();
      const opps = await page.getByTestId("home-opportunities").boundingBox();
      expect(chart && opps && chart.y < opps.y).toBe(true);
    }
    if (info.project.name === "desktop-1440") {
      // Acima da dobra em 1440 × 900: gráfico com ao menos 360 px e as três primeiras oportunidades.
      const chart = await page.getByTestId("home-chart").boundingBox();
      expect(chart && chart.height >= 360 && chart.y + chart.height <= 900).toBe(true);
      for (let i = 0; i < 3; i++) {
        const box = await rows.nth(i).boundingBox();
        expect(box && box.y + box.height <= 900, `oportunidade ${i + 1} acima da dobra`).toBe(true);
      }
    }
    await page.screenshot({ path: `dev/screenshots/home-${info.project.name}.png`, fullPage: true });
  });

  test("movimento reduzido: nenhuma animação se repete em nenhuma rota depois de carregar", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    for (const [path, heading] of ROUTES) {
      await page.goto(path);
      await expect(page.getByRole("heading", { level: 1, name: heading })).toBeVisible();
      const repeating = await page.evaluate(() =>
        document.getAnimations().filter((a) => a.effect?.getComputedTiming().iterations === Infinity).map((a) => (a as CSSAnimation).animationName),
      );
      expect(repeating, path).toEqual([]);
    }
  });

  test("price cards keep one context: the reference is shown apart, with the source name", async ({ page }) => {
    await page.goto("/mercados");
    const card = page.getByTestId("price-card-USDPYG");
    await expect(card).toContainText("Dinheiro físico");
    await expect(card).toContainText("Cambios Alberdi");
    await expect(card).toContainText("≈ BCP (referência)");
    await expect(card).toContainText("BCP");
  });

  test("connection indicator shows demo state and quote age is separate", async ({ page }) => {
    await page.goto("/mercados");
    const status = page.getByTestId("connection-status");
    await expect(status).toHaveAttribute("data-state", "demo");
    await expect(page.getByText(/há \d+ (s|min|h|d)/).first()).toBeVisible();
  });

  test("navigation reaches every screen", async ({ page }) => {
    for (const [path, heading] of ROUTES) {
      await page.goto(path);
      await expect(page.getByRole("heading", { level: 1, name: heading })).toBeVisible();
    }
  });

  test("no route scrolls horizontally (DS25)", async ({ page }) => {
    for (const [path, heading] of ROUTES) {
      await page.goto(path);
      await expect(page.getByRole("heading", { level: 1, name: heading })).toBeVisible();
      await expectNoHorizontalScroll(page);
    }
  });

  test("mobile «Mais» menu reaches the screens outside the bottom bar", async ({ page }, info) => {
    test.skip(info.project.name !== "mobile-390", "só na largura de celular");
    await page.goto("/");
    await page.getByTestId("mobile-nav").getByRole("button", { name: "Mais telas" }).click();
    const menu = page.getByTestId("more-menu");
    await expect(menu).toBeVisible();
    for (const label of ["Monitor ao vivo", "Alertas", "Conhecimento", "Memória", "Configurações"]) await expect(menu.getByRole("link", { name: label })).toBeVisible();
    await menu.getByRole("link", { name: "Memória" }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Memória" })).toBeVisible();
  });

  test("unknown route shows the pt-BR not-found page inside the shell", async ({ page }) => {
    await page.goto("/nao-existe");
    await expect(page.getByRole("heading", { level: 2, name: "Esta página não existe" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Ir para o início" })).toBeVisible();
  });

  test("simulator form validates and returns rankings", async ({ page }, info) => {
    await page.goto("/simulador");
    const capital = page.getByLabel("Capital (BRL)");
    await capital.fill("100");
    await expect(page.getByRole("alert").filter({ hasText: "Informe" })).toContainText("entre R$ 5.000 e R$ 50.000");
    await capital.fill("5000");
    await page.getByRole("button", { name: "Simular rotas" }).click();
    await expect(page.getByTestId("search-summary")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Ranking principal" })).toBeVisible();
    await page.screenshot({ path: `dev/screenshots/simulador-${info.project.name}.png`, fullPage: true });
  });

  test("route detail shows steps, costs and ranking reason", async ({ page }) => {
    await page.goto("/oportunidades");
    await page.getByRole("row", { name: /Abrir detalhes/ }).first().click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await expect(dialog.getByText(/Capital alocado/)).toBeVisible();
    await expect(dialog.getByText(/Ranking (principal|secundário)/)).toBeVisible();
    await expect(dialog.locator("ol li").first()).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
  });

  test("micro-gains are not rounded to zero", async ({ page }) => {
    await page.goto("/oportunidades");
    const cells = page.getByTestId("gain-cell");
    await expect(cells.first()).toBeVisible();
    expect(await cells.count()).toBeGreaterThan(0);
    for (const t of await cells.allTextContents()) expect(t).not.toMatch(/\b0,00\b/);
  });

  test("live cycles of incomplete estimate never carry a «+» in ROI/dia either (Q-07)", async ({ page }) => {
    await page.goto("/oportunidades");
    await page.getByRole("tab", { name: "Cruzamento ao vivo" }).click();
    // incomplete estimates are included by default
    await expect(page.getByTestId("live-cycles").getByRole("switch", { name: /Incluir ciclos com custo pendente/ })).toBeChecked();
    const rows = page.getByTestId("live-cycles").getByTestId("cycle-row").filter({ has: page.getByTestId("roi-day-cell").filter({ hasText: "≈" }) });
    await expect(rows.first()).toBeVisible();
    for (const cell of await rows.getByTestId("roi-day-cell").all()) await expect(cell).not.toContainText("+");
  });

  test("incomplete estimates are never shown as confirmed profit", async ({ page }) => {
    await page.goto("/oportunidades");
    await page.getByRole("tab", { name: /Secundário/ }).click();
    const incomplete = page.getByTestId("gain-cell").filter({ hasText: "não confirmado" });
    const count = await incomplete.count();
    for (let i = 0; i < count; i++) {
      await expect(incomplete.nth(i)).toContainText("≈");
      await expect(incomplete.nth(i)).not.toContainText("+");
    }
    await expect(page.getByText("Estimativa incompleta")).toHaveCount(0);
  });

  test("theme toggle switches to light", async ({ page }) => {
    await page.goto("/configuracoes");
    await page.getByRole("button", { name: "Alternar tema" }).click();
    await expect(page.locator("html")).not.toHaveClass(/dark/);
  });

  test("settings offer real, simulation and demo modes and show the backend status", async ({ page }) => {
    await page.goto("/configuracoes");
    await expect(page.getByTestId("backend-status")).toBeVisible();
    await page.getByLabel("Preferência").click();
    for (const opt of ["Automático", "Real", "Simulação", "Demonstração"]) await expect(page.getByRole("option", { name: opt })).toBeVisible();
    await page.getByRole("option", { name: "Simulação" }).click();
    await expect(page.getByTestId("effective-mode")).toHaveText("simulação");
    await expect(page.getByTestId("simulation-banner")).toBeVisible();
    await expect(page.getByTestId("demo-banner")).toHaveCount(0);
  });
});

test.describe("Contas e diário (demonstração)", () => {
  test("creating an account closes the dialog after the result and marks it as session-only", async ({ page }) => {
    await page.goto("/contas");
    await expect(page.getByTestId("accounts-note")).toContainText("Nada aqui executa operações");
    await page.getByRole("button", { name: "Cadastrar conta" }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByLabel("Instituição").fill("Banco Teste");
    await dialog.getByLabel("Rótulo").fill("Conta e2e");
    await dialog.getByLabel("Saldo livre").fill("1.234,50");
    await dialog.getByRole("button", { name: "Salvar" }).click();
    await expect(dialog).toBeHidden();
    const card = page.getByTestId("account-card").filter({ hasText: "Conta e2e" });
    await expect(card).toBeVisible();
    await expect(card).toContainText("1.234,50");
    await expect(card).toContainText("só nesta sessão");
  });

  test("journal note is saved through the client and listed with the demo badge", async ({ page }) => {
    await page.goto("/diario");
    await expect(page.getByTestId("journal-mode")).toHaveText("demonstração");
    await page.getByLabel("Nova nota").fill("Nota e2e do diário");
    await page.getByRole("button", { name: "Registrar" }).click();
    const entry = page.getByTestId("journal-entry").filter({ hasText: "Nota e2e do diário" });
    await expect(entry).toBeVisible();
    await expect(entry).toContainText("demonstração");
    await expect(page.getByLabel("Nova nota")).toHaveValue("");
  });

  test("evidence highlighted by the URL is marked in the table", async ({ page }) => {
    await page.goto("/fontes?evidence=demo-ev-3");
    const row = page.locator('[data-testid="evidence-row"][data-highlight="true"]');
    await expect(row).toBeVisible();
    await expect(row).toContainText("demo-ev-3");
  });
});

test("live cycle crossing lists cycles starting from parked balances, with mode and confidence", async ({ page }) => {
  await page.goto("/oportunidades");
  await page.getByRole("tab", { name: "Cruzamento ao vivo" }).click();
  const card = page.getByTestId("live-cycles");
  await expect(card).toBeVisible();
  await expect(card.getByTestId("cycles-mode")).toHaveText("demonstração");
  const row = card.getByTestId("cycle-row").first();
  await expect(row).toContainText("@");
  await expect(row.getByText(/Cotado|Estimado|Custo desconhecido/)).toBeVisible();
});
