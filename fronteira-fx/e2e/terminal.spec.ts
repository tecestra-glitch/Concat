import { expect, test } from "@playwright/test";

// Never rely on networkidle: the app may keep a live stream open.
test.describe("Fronteira FX terminal", () => {
  test("home renders prices, ranking and demo banner without horizontal scroll", async ({ page }, info) => {
    await page.goto("/");
    await expect(page.getByTestId("demo-banner")).toBeVisible();
    await expect(page.getByTestId("price-card-USDPYG")).toBeVisible();
    await expect(page.getByTestId("price-card-BRLPYG")).toContainText("por 1 BRL");
    await expect(page.getByRole("heading", { level: 2, name: "Visão geral" })).toBeVisible();
    await expect(page.getByTestId("sources-status")).toBeVisible();
    const scrollW = await page.evaluate(() => document.documentElement.scrollWidth);
    const clientW = await page.evaluate(() => document.documentElement.clientWidth);
    expect(scrollW).toBeLessThanOrEqual(clientW + 1);
    await page.screenshot({ path: `dev/screenshots/home-${info.project.name}.png`, fullPage: true });
  });

  test("connection indicator shows demo state and quote age is separate", async ({ page }) => {
    await page.goto("/");
    const status = page.getByTestId("connection-status");
    await expect(status).toHaveAttribute("data-state", "demo");
    await expect(page.getByText(/há \d+ (s|min|h|d)/).first()).toBeVisible();
  });

  test("navigation reaches every screen", async ({ page }) => {
    for (const [path, heading] of [
      ["/mercados", "Mercados"],
      ["/oportunidades", "Oportunidades"],
      ["/simulador", "Simulador de rotas"],
      ["/contas", "Contas e cartões"],
      ["/fontes", "Fontes"],
      ["/diario", "Diário de operações"],
      ["/configuracoes", "Configurações"],
    ] as const) {
      await page.goto(path);
      await expect(page.getByRole("heading", { level: 2, name: heading })).toBeVisible();
    }
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
    const cells = page.locator("td.tnum.font-semibold");
    const texts = await cells.allTextContents();
    for (const t of texts) expect(t).not.toMatch(/R\$ 0,00$/);
  });

  test("theme toggle switches to light", async ({ page }) => {
    await page.goto("/configuracoes");
    await page.getByRole("button", { name: "Ativar tema claro" }).click();
    await expect(page.locator("html")).not.toHaveClass(/dark/);
  });
});

test("live cycle crossing lists cycles starting from parked balances", async ({ page }) => {
  await page.goto("/oportunidades");
  await page.getByRole("tab", { name: "Cruzamento ao vivo" }).click();
  const card = page.getByTestId("live-cycles");
  await expect(card).toBeVisible();
  await expect(card.getByRole("row").nth(1)).toContainText("@");
});
