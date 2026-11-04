import { expect, test, type Page } from "@playwright/test";

// Never rely on networkidle: the app may keep a live stream open.
async function expectNoHorizontalScroll(page: Page) {
  const scrollW = await page.evaluate(() => document.documentElement.scrollWidth);
  const clientW = await page.evaluate(() => document.documentElement.clientWidth);
  expect(scrollW).toBeLessThanOrEqual(clientW + 1);
}

test.describe("Monitor ao vivo", () => {
  test("renders heading, stats, at least 5 sources and the timeline without horizontal scroll", async ({ page }, info) => {
    await page.goto("/monitor");
    await expect(page.getByRole("heading", { level: 1, name: "Monitor ao vivo" })).toBeVisible();
    await expect(page.getByTestId("watch-stats")).toBeVisible();
    const rows = page.getByTestId("watch-row").filter({ visible: true });
    await expect.poll(() => rows.count()).toBeGreaterThanOrEqual(5);
    await expect(page.getByTestId("change-timeline").getByRole("listitem").first()).toBeVisible();
    await expect(page.getByTestId("change-timeline").getByRole("link", { name: /evidência/ }).first()).toHaveAttribute("href", /\/fontes\?evidence=/);
    await expectNoHorizontalScroll(page);
    await page.screenshot({ path: `dev/screenshots/monitor-${info.project.name}.png`, fullPage: true });
  });

  test("next-run countdown is formatted and ticks", async ({ page }) => {
    await page.goto("/monitor");
    const next = page.getByTestId("next-run").filter({ visible: true }).first();
    await expect(next).toHaveText(/^(em (\d+ s|\d+:\d{2}|\d+ h \d{2} min)|agora)$/);
    const first = await next.textContent();
    await expect.poll(async () => next.textContent(), { timeout: 10_000 }).not.toBe(first);
  });

  test("Sondar agora updates the row and prepends the change to the timeline", async ({ page }) => {
    await page.goto("/monitor");
    const row = page.getByTestId("watch-row").filter({ visible: true }).filter({ has: page.getByText("Cambios Chaco", { exact: true }) }).first();
    await expect(row).toBeVisible();
    const before = await row.getAttribute("data-last-run");
    expect(before).toBeTruthy();
    await row.getByRole("button", { name: /Sondar agora/ }).click();
    await expect.poll(() => row.getAttribute("data-last-run")).not.toBe(before);
    const after = await row.getAttribute("data-last-run");
    expect(Date.parse(after!)).toBeGreaterThan(Date.parse(before!));
    await expect(row.getByText("mudança detectada")).toBeVisible();
    const first = page.getByTestId("change-timeline").getByRole("listitem").first();
    await expect(first).toContainText("Cambios Chaco");
    await expect(first).toContainText("sondagem manual");
  });

  test("disabling a source pauses its countdown (optimistic)", async ({ page }) => {
    await page.goto("/monitor");
    const row = page.getByTestId("watch-row").filter({ visible: true }).filter({ has: page.getByText("Cambios Alberdi", { exact: true }) }).first();
    await row.getByRole("switch", { name: "Monitorar Cambios Alberdi" }).click();
    await expect(row.getByText("pausada")).toBeVisible();
  });

  test("timeline filters by kind", async ({ page }) => {
    await page.goto("/monitor");
    const timeline = page.getByTestId("change-timeline");
    await timeline.getByLabel("Tipo").click();
    await page.getByRole("option", { name: "layout" }).click();
    const items = timeline.getByRole("listitem");
    await expect.poll(() => items.count()).toBeGreaterThanOrEqual(1);
    for (const text of await items.allTextContents()) expect(text).toContain("layout");
  });
});

test.describe("Alertas", () => {
  test("renders rules, events and the demo note without horizontal scroll", async ({ page }, info) => {
    await page.goto("/alertas");
    await expect(page.getByRole("heading", { level: 1, name: "Alertas" })).toBeVisible();
    await expect(page.getByTestId("alerts-demo-note")).toBeVisible();
    await expect.poll(() => page.getByTestId("alert-rule").filter({ visible: true }).count()).toBeGreaterThanOrEqual(4);
    await expect.poll(() => page.getByTestId("alert-event").count()).toBeGreaterThanOrEqual(5);
    await expect(page.getByTestId("alert-rules")).toContainText("0,20 %");
    await expect(page.getByTestId("alert-rules")).toContainText("15 min");
    await expectNoHorizontalScroll(page);
    await page.screenshot({ path: `dev/screenshots/alertas-${info.project.name}.png`, fullPage: true });
  });

  test("rule dialog validates threshold and target, then adds a row", async ({ page }) => {
    await page.goto("/alertas");
    await page.getByRole("button", { name: "Nova regra" }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    const submit = dialog.getByRole("button", { name: "Criar regra" });
    await expect(submit).toBeDisabled();

    await dialog.getByLabel("Nome").fill("Teste e2e");
    const threshold = dialog.getByLabel("Limite (%)");
    await threshold.fill("abc");
    await expect(dialog.getByRole("alert")).toContainText("percentual");
    await expect(submit).toBeDisabled();
    await threshold.fill("0,3");
    await expect(dialog.getByRole("alert")).toHaveCount(0);
    await expect(submit).toBeEnabled();

    // Target appears only for channels that need one, with help text.
    await expect(dialog.getByLabel("Chat do Telegram")).toHaveCount(0);
    await dialog.getByLabel("Canal").click();
    await page.getByRole("option", { name: "Telegram" }).click();
    const target = dialog.getByLabel("Chat do Telegram");
    await expect(target).toBeVisible();
    await expect(dialog.getByText(/token do bot/)).toBeVisible();
    await expect(submit).toBeDisabled();
    await target.fill("abc");
    await expect(dialog.getByRole("alert")).toContainText("chat_id");
    await target.fill("123456789");
    await expect(submit).toBeEnabled();
    await submit.click();
    await expect(dialog).toBeHidden();

    const row = page.getByTestId("alert-rule").filter({ visible: true }).filter({ hasText: "Teste e2e" });
    await expect(row).toBeVisible();
    await expect(row).toContainText("0,30 %");
    await expect(row).toContainText("Telegram");
    await expect(row).toContainText("10 min");
  });

  test("editing a rule saves through the client and closes after the result", async ({ page }) => {
    await page.goto("/alertas");
    const row = page.getByTestId("alert-rule").filter({ visible: true }).filter({ hasText: "Ciclo acima de 0,2 %" });
    await expect(row).toBeVisible();
    await row.getByRole("button", { name: /^Editar: / }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByLabel("Limite (%)")).toHaveValue("0,2");
    await dialog.getByLabel("Nome").fill("Ciclo acima de 0,2 % (editada)");
    await dialog.getByLabel("Limite (%)").fill("0,35");
    await dialog.getByRole("button", { name: "Salvar alterações" }).click();
    await expect(dialog).toBeHidden();
    const edited = page.getByTestId("alert-rule").filter({ visible: true }).filter({ hasText: "(editada)" });
    await expect(edited).toBeVisible();
    await expect(edited).toContainText("0,35 %");
  });

  test("deleting a rule asks for confirmation and removes the row", async ({ page }) => {
    await page.goto("/alertas");
    const rows = page.getByTestId("alert-rule").filter({ visible: true });
    await expect.poll(() => rows.count()).toBeGreaterThanOrEqual(4);
    const before = await rows.count();
    const row = rows.filter({ hasText: "Nova oportunidade ≥ 0,1 %" });
    await row.getByRole("button", { name: /^Excluir: / }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toContainText("Excluir a regra");
    await dialog.getByRole("button", { name: "Excluir regra" }).click();
    await expect(dialog).toBeHidden();
    await expect.poll(() => rows.count()).toBe(before - 1);
    await expect(page.getByTestId("alert-rule").filter({ hasText: "Nova oportunidade ≥ 0,1 %" })).toHaveCount(0);
  });

  test("stat row counts changes within 24 h", async ({ page }) => {
    await page.goto("/monitor");
    await expect(page.getByTestId("changes-24h")).toHaveText(/de \d+ nas últimas 24 h/);
  });

  test("Testar records a not-sent event in demo mode", async ({ page }) => {
    await page.goto("/alertas");
    const rows = page.getByTestId("alert-rule").filter({ visible: true });
    await expect(rows.first()).toBeVisible();
    await rows.first().getByRole("button", { name: /Testar/ }).click();
    const first = page.getByTestId("alert-event").first();
    await expect(first).toContainText("nada foi enviado");
    await expect(first).toContainText("não enviado");
  });
});
