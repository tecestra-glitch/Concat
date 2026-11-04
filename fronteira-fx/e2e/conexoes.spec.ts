import { expect, test, type Page } from "@playwright/test";

// Never rely on networkidle: the app keeps a live stream open.
async function expectNoHorizontalScroll(page: Page) {
  const scrollW = await page.evaluate(() => document.documentElement.scrollWidth);
  const clientW = await page.evaluate(() => document.documentElement.clientWidth);
  expect(scrollW).toBeLessThanOrEqual(clientW + 1);
}

test.describe("conexões (demonstração)", () => {
  test("rota, banner de não pedir senha e nenhum campo de senha", async ({ page }) => {
    await page.goto("/conexoes");
    await expect(page.getByRole("heading", { level: 1, name: "Conexões" })).toBeVisible();
    await expect(page.getByTestId("no-password-banner")).toContainText("O Fronteira FX nunca pede a senha do seu banco.");
    await expect(page.locator('input[type="password"]')).toHaveCount(0);
    await expectNoHorizontalScroll(page);
  });

  test("lista os quatro grupos e mostra o aviso de agregador no Open Finance", async ({ page }) => {
    await page.goto("/conexoes");
    for (const t of ["Bancos do Brasil", "Contas globais", "Paraguai", "Corretoras de cripto"]) {
      await expect(page.getByRole("heading", { level: 2, name: t })).toBeVisible();
    }
    const nubank = page.getByTestId("institution-card").filter({ hasText: "Nubank" });
    await expect(nubank.getByRole("button", { name: "Autorizar pelo Open Finance" })).toBeDisabled();
    await expect(nubank).toContainText("Precisa contratar um agregador de Open Finance");
  });

  test("abre o formulário de chave só leitura com passo a passo e recusa validação vazia", async ({ page }) => {
    await page.goto("/conexoes");
    const binance = page.getByTestId("institution-card").filter({ hasText: "Binance" });
    await binance.getByRole("button", { name: "Chave de API só leitura" }).click();
    const dialog = page.getByRole("dialog", { name: /Chave de API só leitura: Binance/ });
    await expect(dialog).toBeVisible();
    await expect(dialog).toContainText("O Fronteira FX nunca pede a senha do seu banco.");
    await expect(dialog.getByTestId("api-key-steps").getByText(/DESMARCADOS operar/)).toBeVisible();
    await expect(dialog.locator('input[type="password"]')).toHaveCount(0);
    await dialog.getByRole("button", { name: "Validar chave" }).click();
    await expect(dialog.getByRole("alert").first()).toContainText("Informe a chave de API");
    await expect(dialog.getByRole("button", { name: "Salvar conexão" })).toBeDisabled();
  });

  test("chave de demonstração que pode operar é recusada e não libera salvar", async ({ page }) => {
    await page.goto("/conexoes");
    const binance = page.getByTestId("institution-card").filter({ hasText: "Binance" });
    await binance.getByRole("button", { name: "Chave de API só leitura" }).click();
    const dialog = page.getByRole("dialog", { name: /Binance/ });
    await dialog.getByLabel("Chave de API").fill("demo-trade-0123456789abcdef");
    await dialog.getByLabel("Segredo da API").fill("segredo-demo-0123456789abcd");
    await dialog.getByRole("checkbox").check();
    await dialog.getByRole("button", { name: "Validar chave" }).click();
    await expect(dialog.getByTestId("api-key-refused")).toContainText("Chave recusada");
    await expect(dialog.getByRole("button", { name: "Salvar conexão" })).toBeDisabled();
  });

  test("conexão existente mostra só os últimos 4 caracteres da chave", async ({ page }) => {
    await page.goto("/conexoes");
    const row = page.getByTestId("connection-row").first();
    await expect(row).toContainText("••••9f2K");
    await expect(row).not.toContainText("9f2K9f2K");
  });
});

test.describe("conexões no celular", () => {
  test("390 px: sem rolagem horizontal e menu Conexões acessível", async ({ page }, info) => {
    test.skip(info.project.name !== "mobile-390", "só no projeto de celular");
    await page.goto("/conexoes");
    await expect(page.getByRole("heading", { level: 1, name: "Conexões" })).toBeVisible();
    await expectNoHorizontalScroll(page);
  });
});
