import { expect, test, type Page } from "@playwright/test";

// Never rely on networkidle: the app keeps a live stream open.
async function expectNoHorizontalScroll(page: Page) {
  const scrollW = await page.evaluate(() => document.documentElement.scrollWidth);
  const clientW = await page.evaluate(() => document.documentElement.clientWidth);
  expect(scrollW).toBeLessThanOrEqual(clientW + 1);
}

test.describe("Economia e cripto (módulo market)", () => {
  test("mostra manchetes com link externo seguro, referências com aviso e selo de volatilidade", async ({ page }) => {
    await page.goto("/economia");
    await expect(page.getByRole("heading", { level: 1, name: "Economia e cripto" })).toBeVisible();
    await expect(page.getByTestId("news-item").first()).toBeVisible();
    await expect.poll(() => page.getByTestId("news-item").count()).toBeGreaterThanOrEqual(3);

    const link = page.getByTestId("news-item").first().getByRole("link");
    await expect(link).toHaveAttribute("target", "_blank");
    await expect(link).toHaveAttribute("rel", "noopener noreferrer");

    await expect(page.getByRole("note").filter({ hasText: "Não é preço executável" })).toBeVisible();
    const cards = page.getByTestId("reference-card");
    await expect.poll(() => cards.count()).toBeGreaterThanOrEqual(3);
    await expect(page.getByTestId("volatility-detail").first()).toBeVisible();
    await expect(page.getByText("Demonstração: dados ilustrativos").first()).toBeVisible();

    await expectNoHorizontalScroll(page);
  });

  test("filtro de fonte esvazia e volta sem erro", async ({ page }) => {
    await page.goto("/economia");
    await expect(page.getByTestId("news-item").first()).toBeVisible();
    await page.getByLabel("Fonte").click();
    await page.getByRole("option", { name: "Banco Central" }).click();
    await expect(page.getByText("Nenhuma manchete para esta fonte.")).toBeVisible();
    await page.getByLabel("Fonte").click();
    await page.getByRole("option", { name: "Todas" }).click();
    await expect(page.getByTestId("news-item").first()).toBeVisible();
  });

  test("tela e navegação existem nos três tamanhos (screenshot)", async ({ page }, info) => {
    await page.goto("/economia");
    await expect(page.getByRole("heading", { level: 1, name: "Economia e cripto" })).toBeVisible();
    await expect(page.getByTestId("reference-card").first()).toBeVisible();
    await expectNoHorizontalScroll(page);
    await page.screenshot({ path: `dev/screenshots/economia-${info.project.name}.png`, fullPage: true });
  });
});
