import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

// Never rely on networkidle: the app keeps a live stream open.
async function expectNoHorizontalScroll(page: Page) {
  const scrollW = await page.evaluate(() => document.documentElement.scrollWidth);
  const clientW = await page.evaluate(() => document.documentElement.clientWidth);
  expect(scrollW).toBeLessThanOrEqual(clientW + 1);
}

async function seriousViolations(page: Page): Promise<string[]> {
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).exclude("canvas").analyze();
  return results.violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => `${v.id} (${v.impact}): ${v.help} → ${v.nodes.slice(0, 3).map((n) => n.target.join(" ")).join(" | ")}`);
}

/** Abre o cruzamento ao vivo e gera um plano a partir do primeiro ciclo lucrativo (demonstração). */
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

test.describe("planos de execução (demonstração, nada executa)", () => {
  test("gera, aprova, conclui os passos e vê esperado × realizado; sem rolagem horizontal e sem erro de acessibilidade", async ({ page }, info) => {
    await gerarPlano(page);
    await expect(page.getByTestId("plan-status")).toHaveText("Proposto");
    await expect(page.getByTestId("no-money-notice")).toContainText("Aprovar não move dinheiro");
    await expect(page.getByTestId("plan-countdown")).toContainText("Cotação válida por mais");
    await expectNoHorizontalScroll(page);
    expect(await seriousViolations(page)).toEqual([]);

    await page.getByTestId("approve-plan").click();
    await expect(page.getByTestId("plan-status")).toHaveText("Aprovado");

    const total = await page.getByTestId("plan-step").count();
    expect(total).toBeGreaterThan(0);
    for (let i = 1; i <= total; i++) {
      const next = page.locator('[data-testid="plan-step"][data-next="true"]');
      await next.getByLabel(/Valor realizado/).fill("1000");
      await next.getByRole("button", { name: "Marcar como feito" }).click();
      await expect(page.getByTestId("plan-progress")).toContainText(`${i} de ${total}`);
    }
    await expect(page.getByTestId("plan-status")).toHaveText("Concluído");
    await expect(page.getByTestId("plan-result")).toContainText("Esperado");
    await expect(page.getByTestId("plan-result")).toContainText("Realizado");
    await expectNoHorizontalScroll(page);
    await page.screenshot({ path: `dev/screenshots/plano-${info.project.name}.png`, fullPage: true });
  });

  test("recusar um plano proposto o encerra e tira os botões de decisão", async ({ page }) => {
    await gerarPlano(page);
    await page.getByTestId("reject-plan").click();
    await expect(page.getByTestId("plan-status")).toHaveText("Recusado");
    await expect(page.getByTestId("approve-plan")).toBeDisabled();
    await expect(page.getByTestId("reject-plan")).toBeDisabled();
  });

  test("a lista de planos mostra o plano gerado", async ({ page }) => {
    await gerarPlano(page);
    // A demonstração guarda os planos na memória da página: a navegação precisa ser interna, sem recarregar.
    await page.getByRole("link", { name: "Todos os planos" }).click();
    await expect(page).toHaveURL(/\/planos$/);
    await expect(page.getByRole("heading", { level: 2, name: "Planos" })).toBeVisible();
    await expect(page.getByTestId("plan-row").first()).toContainText("Proposto");
    expect(await seriousViolations(page)).toEqual([]);
  });
});

test.describe("configurações: alerta de oportunidade e premissas", () => {
  test("cria o limite de ganho líquido em dinheiro e mostra as premissas com fonte e verificação", async ({ page }, info) => {
    await page.goto("/configuracoes");
    await expect(page.getByRole("heading", { level: 2, name: "Configurações" })).toBeVisible();
    await expect(page.getByTestId("net-gain-status")).toContainText("Sem limite");
    await page.getByLabel("Ganho líquido mínimo").fill("20");
    await page.getByRole("button", { name: "Criar limite" }).click();
    await expect(page.getByText("Limite salvo.")).toBeVisible();
    await expect(page.getByTestId("net-gain-status")).toContainText("R$ 20,00");

    await expect(page.getByTestId("premissa-route")).toHaveCount(5);
    await expect(page.getByTestId("premissa-rail")).toHaveCount(9);
    await expect(page.getByTestId("premissas").getByText("não verificado").first()).toBeVisible();
    await expect(page.getByTestId("premissas")).toContainText("Foz do Iguaçu");
    await expectNoHorizontalScroll(page);
    expect(await seriousViolations(page)).toEqual([]);
    await page.screenshot({ path: `dev/screenshots/configuracoes-${info.project.name}.png`, fullPage: true });
  });

  test("valor inválido no limite não salva e explica o que digitar", async ({ page }) => {
    await page.goto("/configuracoes");
    await page.getByLabel("Ganho líquido mínimo").fill("-5");
    await page.getByRole("button", { name: "Criar limite" }).click();
    await expect(page.getByText("igual a zero ou maior")).toBeVisible();
  });
});
