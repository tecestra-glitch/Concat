import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { ROUTES } from "./routes";

// Never rely on networkidle: wait for the page heading and for the skeletons to leave.
test.describe("Acessibilidade (axe, tema escuro)", () => {
  for (const [path, heading] of ROUTES) {
    test(`sem violações serious/critical em ${path}`, async ({ page }) => {
      await page.goto(path);
      await expect(page.getByRole("heading", { level: 2, name: heading })).toBeVisible();
      await expect(page.locator('[role="status"][aria-label^="Carregando"]')).toHaveCount(0, { timeout: 15_000 });
      const results = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
        .exclude("canvas")
        .analyze();
      const blocking = results.violations
        .filter((v) => v.impact === "serious" || v.impact === "critical")
        .map((v) => `${v.id} (${v.impact}): ${v.help} → ${v.nodes.slice(0, 3).map((n) => n.target.join(" ")).join(" | ")}`);
      expect(blocking).toEqual([]);
    });
  }
});
