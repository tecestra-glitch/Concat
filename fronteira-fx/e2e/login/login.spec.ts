import { expect, test } from "@playwright/test";

// Servidor próprio (porta PORT+1, ver playwright.config.ts) com login ligado. Senha só de teste.
const PASSWORD = "senha-e2e-fronteira-2026";

test.describe("login próprio", () => {
  test("sem sessão, páginas vão para /entrar com o destino pedido", async ({ page }) => {
    await page.goto("/contas");
    await expect(page).toHaveURL(/\/entrar\?para=%2Fcontas$/);
    await expect(page.getByRole("heading", { name: "Fronteira FX" })).toBeVisible();
    await expect(page.getByLabel("Senha")).toBeFocused();
    await expect(page.getByLabel("Lembrar por 30 dias")).toBeChecked();
    await expect(page.getByRole("button", { name: "Entrar" })).toBeVisible();
  });

  test("/api/fx sem sessão responde 401 em JSON", async ({ request }) => {
    const res = await request.get("/api/fx/v1/sources", { maxRedirects: 0 });
    expect(res.status()).toBe(401);
    expect(res.headers()["content-type"]).toContain("application/json");
  });

  test("senha errada mostra erro genérico e não entra", async ({ page }) => {
    await page.goto("/entrar?para=%2Fcontas");
    await page.getByLabel("Senha").fill("senha-errada");
    await page.getByRole("button", { name: "Entrar" }).click();
    await expect(page.locator("#entrar-erro")).toHaveText("Não foi possível entrar. Confira a senha e tente de novo.");
    await expect(page).toHaveURL(/\/entrar/);
  });

  test("senha certa entra e volta para a página pedida; sair encerra a sessão", async ({ page }) => {
    await page.goto("/contas");
    await page.getByLabel("Senha").fill(PASSWORD);
    await page.getByRole("button", { name: "Entrar" }).click();
    await expect(page).toHaveURL(/\/contas$/);
    await expect(page.getByRole("heading", { name: "Contas e cartões" })).toBeVisible();

    const cookies = await page.context().cookies();
    const session = cookies.find((c) => c.name === "fx_sessao");
    expect(session?.httpOnly).toBe(true);
    expect(session?.sameSite).toBe("Lax");

    await page.getByRole("button", { name: "Sair" }).click();
    await expect(page).toHaveURL(/\/entrar$/);
    await page.goto("/contas");
    await expect(page).toHaveURL(/\/entrar\?para=%2Fcontas$/);
  });
});
