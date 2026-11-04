import { expect, test } from "@playwright/test";

/**
 * Telas do triangulador (Triângulos, Mercado global, Indicadores, Notícias) nos três tamanhos (1440, 1024, 390).
 * Confere: título da rota, nenhuma rolagem horizontal da página, nenhum botão de ordem, e rótulo de referência ou
 * executável visível. O axe (serious/critical) já roda para estas rotas em `a11y.spec.ts` (lista ROUTES).
 * Nunca espera por rede ociosa: espera pelo título e pelos esqueletos.
 */
const SCREENS = [
  { path: "/triangulos", heading: "Triângulos", labelRequired: false },
  { path: "/global", heading: "Mercado global", labelRequired: true },
  { path: "/indicadores", heading: "Indicadores", labelRequired: true },
  { path: "/noticias", heading: "Notícias", labelRequired: true },
] as const;

for (const screen of SCREENS) {
  test(`${screen.path}: sem rolagem horizontal, sem ordem e com rótulo`, async ({ page }) => {
    await page.goto(screen.path);
    await expect(page.getByRole("heading", { level: 1, name: screen.heading })).toBeVisible();
    await expect(page.locator('[role="status"][aria-label^="Carregando"]')).toHaveCount(0, { timeout: 15_000 });

    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow, `${screen.path} tem rolagem horizontal`).toBeLessThanOrEqual(0);

    await expect(page.getByRole("button", { name: /comprar|vender|ordem|buy|sell/i })).toHaveCount(0);

    const labels = page.getByText(/Referência · não executável|^Executável$/);
    if (screen.labelRequired) {
      await expect(labels.first()).toBeVisible();
    }
  });
}

test("/triangulos: cada triângulo mostra o rótulo e a fonte", async ({ page }) => {
  await page.goto("/triangulos");
  await expect(page.getByRole("heading", { level: 1, name: "Triângulos" })).toBeVisible();
  await expect(page.locator('[role="status"][aria-label^="Carregando"]')).toHaveCount(0, { timeout: 15_000 });
  const cards = page.getByTestId("triangle-card");
  const n = await cards.count();
  for (let i = 0; i < n; i++) {
    await expect(cards.nth(i).getByText(/Referência · não executável|^Executável$/).first()).toBeVisible();
    await expect(cards.nth(i).getByText(/Simulação sobre o grafo/)).toBeVisible();
  }
});

test("/noticias: cada manchete mostra fonte e atribuição", async ({ page }) => {
  await page.goto("/noticias");
  await expect(page.getByRole("heading", { level: 1, name: "Notícias" })).toBeVisible();
  await expect(page.locator('[role="status"][aria-label^="Carregando"]')).toHaveCount(0, { timeout: 15_000 });
  const items = page.getByTestId("news-item");
  const n = await items.count();
  for (let i = 0; i < n; i++) {
    await expect(items.nth(i).getByText(/^Fonte:/)).toBeVisible();
    await expect(items.nth(i).getByTestId("news-attribution")).not.toBeEmpty();
  }
});
