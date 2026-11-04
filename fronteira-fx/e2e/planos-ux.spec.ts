import { expect, test, type Page } from "@playwright/test";

// Never rely on networkidle: the app keeps a live stream open.
async function expectNoHorizontalScroll(page: Page) {
  const scrollW = await page.evaluate(() => document.documentElement.scrollWidth);
  const clientW = await page.evaluate(() => document.documentElement.clientWidth);
  expect(scrollW).toBeLessThanOrEqual(clientW + 1);
}

/** Abre o cruzamento ao vivo e gera um plano a partir do primeiro ciclo (demonstração). */
async function gerarPlano(page: Page) {
  await page.goto("/oportunidades");
  await expect(page.getByRole("heading", { level: 2, name: "Oportunidades" })).toBeVisible();
  await page.getByRole("tab", { name: /Cruzamento ao vivo/ }).click();
  await expect(page.getByTestId("live-cycles")).toBeVisible();
  await expect(page.getByTestId("cycle-row").first()).toBeVisible();
  await page.getByRole("button", { name: /^Gerar plano do ciclo/ }).first().click();
  await expect(page).toHaveURL(/\/planos\/demo-plan-\d+$/);
  await expect(page.getByRole("heading", { level: 2, name: "Plano de execução" })).toBeVisible();
}

test.describe("planos: foco, estimativa e celular (demonstração)", () => {
  test("cruzamento: o selo não chama de lucrativo o que tem custo pendente", async ({ page }) => {
    await page.goto("/oportunidades");
    await page.getByRole("tab", { name: /Cruzamento ao vivo/ }).click();
    await expect(page.getByTestId("live-cycles")).toBeVisible();
    const badge = page.getByTestId("cycles-profit");
    await expect(badge).toBeVisible();
    const text = (await badge.textContent()) ?? "";
    // quem tem só ciclo com custo pendente vê "0 confirmados", nunca "N lucrativos" em verde
    if (/estimad/.test(text)) expect(text).toMatch(/^0 confirmados/);
    expect(text).not.toMatch(/^[1-9]\d* lucrativos?$/);
  });

  test("plano com custo pendente mostra a saída como estimativa (≈), não como valor exato", async ({ page }) => {
    await gerarPlano(page);
    await expect(page.getByTestId("plan-incomplete")).toBeVisible();
    await expect(page.getByText("Saída estimada (não confirmada)")).toBeVisible();
  });

  test("aprovar leva o foco ao próximo passo, e não ao topo da página", async ({ page }) => {
    await gerarPlano(page);
    await page.getByTestId("approve-plan").click();
    await expect(page.getByTestId("plan-status")).toHaveText("Aprovado");
    await expect(page.locator('[data-testid="plan-step"][data-next="true"] input').first()).toBeFocused();
  });

  test("concluir um passo leva o foco ao passo seguinte e o status fica numa região que é anunciada", async ({ page }) => {
    await gerarPlano(page);
    await page.getByTestId("approve-plan").click();
    await expect(page.getByTestId("plan-status")).toHaveText("Aprovado");
    const total = await page.getByTestId("plan-step").count();
    const next = page.locator('[data-testid="plan-step"][data-next="true"]');
    await next.getByLabel(/Valor realizado/).fill("1000");
    await next.getByRole("button", { name: "Marcar como feito" }).click();
    await expect(page.getByTestId("plan-progress")).toContainText(`1 de ${total}`);
    if (total > 1) {
      await expect(page.locator('[data-testid="plan-step"][data-next="true"] input').first()).toBeFocused();
    } else {
      await expect(page.getByTestId("plan-result")).toBeFocused();
    }
    // o selo de status fica dentro de uma região viva (anunciada por leitor de tela)
    await expect(page.locator('[aria-live="polite"]').filter({ has: page.getByTestId("plan-status") }).first()).toBeAttached();
  });

  test("no celular, a lista de planos abre cada plano com um toque, sem rolagem lateral", async ({ page }, info) => {
    test.skip(info.project.name !== "mobile-390", "só na largura de celular");
    await gerarPlano(page);
    // navegação interna: recarregar a página zeraria os planos da demonstração (ficam na memória da aba)
    await page.getByRole("link", { name: "Todos os planos" }).click();
    await expect(page).toHaveURL(/\/planos$/);
    const card = page.getByTestId("plan-card").first();
    await expect(card).toBeVisible();
    const box = await card.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.x + box!.width).toBeLessThanOrEqual(390 + 1);
    await expectNoHorizontalScroll(page);
    await card.click();
    await expect(page).toHaveURL(/\/planos\/demo-plan-\d+$/);
  });
});
