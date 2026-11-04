import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { ROUTES } from "./routes";

async function blockingViolations(page: Page): Promise<string[]> {
  // A entrada da rota (fx-enter, opacidade) e outras animações finitas precisam acabar antes do axe: senão ele lê
  // cores no meio do fade. Animações infinitas (esqueleto, giro) ficam de fora, sem esperar para sempre.
  await page.waitForFunction(() => document.getAnimations().every((a) => a.playState !== "running" || a.effect?.getComputedTiming().iterations === Infinity));
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
    .exclude("canvas")
    .analyze();
  return results.violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => `${v.id} (${v.impact}): ${v.help} → ${v.nodes.slice(0, 3).map((n) => n.target.join(" ")).join(" | ")}`);
}

// Never rely on networkidle: wait for the page heading and for the skeletons to leave.
test.describe("Acessibilidade (axe, tema escuro)", () => {
  for (const [path, heading] of ROUTES) {
    test(`sem violações serious/critical em ${path}`, async ({ page }) => {
      await page.goto(path);
      await expect(page.getByRole("heading", { level: 1, name: heading })).toBeVisible();
      await expect(page.locator('[role="status"][aria-label^="Carregando"]')).toHaveCount(0, { timeout: 15_000 });
      expect(await blockingViolations(page)).toEqual([]);
    });
  }
});

/**
 * Pregão nos dois temas e, no celular, com cada aba aberta: painéis ocultos (`max-md:hidden`) não entram na
 * análise do axe, então a aba padrão sozinha deixaria livro, lista e últimas sem verificação de contraste.
 */
test.describe("Acessibilidade do pregão (axe, claro e escuro, cada aba)", () => {
  for (const theme of ["escuro", "claro"] as const) {
    test(`/pregao sem violações serious/critical no tema ${theme}`, async ({ page }, info) => {
      await page.goto("/pregao");
      await expect(page.getByRole("heading", { level: 1, name: "Pregão" })).toBeVisible();
      if (theme === "claro") {
        await page.getByRole("button", { name: "Alternar tema" }).click();
        await expect.poll(() => page.evaluate(() => document.documentElement.classList.contains("dark"))).toBe(false);
      }
      await expect(page.getByTestId("pregao-chart")).toHaveAttribute("data-state", "ready");
      await expect(page.getByTestId("pregao-book")).toHaveAttribute("data-state", "ready");
      await expect(page.getByTestId("pregao-watchlist")).toHaveAttribute("data-state", "ready");
      await expect(page.getByTestId("pregao-prints")).toHaveAttribute("data-state", "ready");
      const tabs = info.project.name === "mobile-390" ? ["Gráfico", "Livro", "Lista", "Últimas"] : [null];
      const found: string[] = [];
      for (const tab of tabs) {
        if (tab) {
          await page.getByRole("tab", { name: tab }).click();
          await expect(page.getByRole("tab", { name: tab })).toHaveAttribute("aria-selected", "true");
        }
        for (const v of await blockingViolations(page)) found.push(`[${tab ?? "página"}] ${v}`);
      }
      expect(found).toEqual([]);
    });
  }
});
