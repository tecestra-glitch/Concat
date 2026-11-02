import { expect, test } from "@playwright/test";

/**
 * Tela de pregão em modo demo (sem backend), nos 3 projetos (1440 / 1024 / 390).
 * Espera sempre por elementos (`data-testid`, `data-state`); nunca por rede ociosa nem por tempo fixo.
 */
test.describe("Pregão", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/pregao");
    await expect(page.getByRole("heading", { level: 2, name: "Pregão" })).toBeVisible();
  });

  test("blocos essenciais e sem rolagem horizontal", async ({ page }, info) => {
    await expect(page.getByTestId("demo-banner")).toBeVisible();
    await expect(page.getByTestId("pregao-demo-note")).toBeVisible();
    await expect(page.getByTestId("pregao-ticker")).toHaveAttribute("data-state", "ready");
    await expect(page.getByTestId("pregao-ticker-item").first()).toBeVisible();
    await expect(page.getByTestId("pregao-clock")).toBeVisible();
    await expect(page.getByTestId("pregao-market-status")).toBeVisible();
    await expect(page.getByTestId("pregao-stats")).toHaveAttribute("data-state", "ready");
    await expect(page.getByTestId("pregao-chart")).toHaveAttribute("data-state", "ready");
    await expect(page.getByTestId("pregao-chart").locator("canvas").first()).toBeVisible();
    const mobile = info.project.name === "mobile-390";
    if (mobile) {
      await expect(page.getByTestId("pregao-tabs")).toBeVisible();
      await expect(page.getByTestId("pregao-book")).toBeHidden();
      await page.getByRole("tab", { name: "Livro" }).click();
      await expect(page.getByTestId("pregao-book")).toBeVisible();
      await expect(page.getByTestId("pregao-heatmap")).toBeVisible();
      await expect(page.getByTestId("pregao-cross")).toBeVisible();
      await page.getByRole("tab", { name: "Lista" }).click();
      await expect(page.getByTestId("pregao-watchlist")).toBeVisible();
      await page.getByRole("tab", { name: "Últimas" }).click();
      await expect(page.getByTestId("pregao-prints")).toBeVisible();
      await page.getByRole("tab", { name: "Gráfico" }).click();
      await expect(page.getByTestId("pregao-chart")).toBeVisible();
    } else {
      await expect(page.getByTestId("pregao-tabs")).toBeHidden();
      for (const id of ["pregao-book", "pregao-heatmap", "pregao-cross", "pregao-prints", "pregao-watchlist"]) await expect(page.getByTestId(id)).toBeVisible();
    }
    const { scrollWidth, clientWidth } = await page.evaluate(() => ({ scrollWidth: document.documentElement.scrollWidth, clientWidth: document.documentElement.clientWidth }));
    expect(scrollWidth).toBeLessThanOrEqual(clientWidth + 1);
    await page.screenshot({ path: `dev/screenshots/pregao-${info.project.name}.png`, fullPage: true });
  });

  test("referência nunca entra nos lados do livro", async ({ page }) => {
    if (test.info().project.name === "mobile-390") await page.getByRole("tab", { name: "Livro" }).click();
    const book = page.getByTestId("pregao-book");
    await expect(book).toHaveAttribute("data-state", "ready");
    await expect(book.getByTestId("pregao-book-side-buy").locator('[data-kind="market_reference"]')).toHaveCount(0);
    await expect(book.getByTestId("pregao-book-side-sell").locator('[data-kind="market_reference"]')).toHaveCount(0);
    await expect(book.getByTestId("pregao-book-reference").getByTestId("pregao-book-ref-row").first()).toBeVisible();
    await expect(book.getByTestId("pregao-book-row").first()).toHaveAttribute("data-best", "true");
  });

  test("atalhos de teclado", async ({ page }) => {
    await expect(page.getByTestId("pregao-chart")).toHaveAttribute("data-state", "ready");
    await page.locator("body").click();
    await page.keyboard.press("2");
    await expect(page.getByTestId("pregao-timeframe").locator('[data-tf="1h"]')).toHaveAttribute("aria-checked", "true");
    await page.keyboard.press("3");
    await expect(page.getByTestId("pregao-timeframe").locator('[data-tf="4h"]')).toHaveAttribute("aria-checked", "true");
    const pairRadio = page.getByTestId("pregao-pair").locator('[aria-checked="true"]');
    const before = await pairRadio.getAttribute("data-pair");
    await page.keyboard.press("]");
    await expect(pairRadio).not.toHaveAttribute("data-pair", before ?? "");
    await page.keyboard.press("?");
    await expect(page.getByRole("dialog", { name: "Atalhos do teclado" })).toBeVisible();
    await expect(page.getByTestId("pregao-shortcuts-list").locator("kbd")).toHaveCount(8);
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toHaveCount(0);
  });

  test("intervalo escolhido sobrevive ao recarregar (fx.pregao.prefs)", async ({ page }) => {
    await page.getByTestId("pregao-timeframe").locator('[data-tf="15m"]').click();
    await expect(page.getByTestId("pregao-chart")).toHaveAttribute("data-tf", "15m");
    await page.reload();
    await expect(page.getByTestId("pregao-timeframe").locator('[data-tf="15m"]')).toHaveAttribute("aria-checked", "true");
    await expect(page.getByTestId("pregao-chart")).toHaveAttribute("data-tf", "15m");
  });

  test("troca de intervalo não recria o gráfico", async ({ page }) => {
    const chart = page.getByTestId("pregao-chart");
    await expect(chart).toHaveAttribute("data-state", "ready");
    await expect(chart.locator("canvas").first()).toBeVisible();
    const before = await chart.locator("canvas").count();
    expect(before).toBeGreaterThan(0);
    await page.getByTestId("pregao-timeframe").locator('[data-tf="1d"]').click();
    await expect(chart).toHaveAttribute("data-tf", "1d");
    await expect(chart).toHaveAttribute("data-state", "ready");
    expect(await chart.locator("canvas").count()).toBe(before);
  });

  test("seleção na lista muda a série do gráfico", async ({ page }) => {
    const mobile = test.info().project.name === "mobile-390";
    await expect(page.getByTestId("pregao-chart")).toHaveAttribute("data-state", "ready");
    if (mobile) await page.getByRole("tab", { name: "Lista" }).click();
    const row = page.locator('[data-testid="pregao-watchlist-row"]:not([aria-disabled="true"])').nth(1);
    await expect(row).toBeVisible();
    const key = await row.getAttribute("data-key");
    expect(key).toBeTruthy();
    await row.click();
    if (mobile) await page.getByRole("tab", { name: "Gráfico" }).click();
    await expect(page.getByTestId("pregao-chart")).toHaveAttribute("data-key", key ?? "");
  });
});
