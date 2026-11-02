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
      // Livro, mapa e últimas cabem no próprio painel: nenhuma tabela passa da borda do painel (nem com rolagem interna).
      await expect(page.getByTestId("pregao-print-row").first()).toBeVisible();
      for (const id of ["pregao-book", "pregao-heatmap", "pregao-prints"]) {
        const overflow = await page.getByTestId(id).evaluate((root) => {
          const box = root.getBoundingClientRect();
          return [...root.querySelectorAll("table")].map((t) => {
            const scroller = t.parentElement!;
            return { tableRight: t.getBoundingClientRect().right - box.right, hidden: scroller.scrollWidth - scroller.clientWidth };
          });
        });
        expect(overflow.length, id).toBeGreaterThan(0);
        for (const o of overflow) {
          expect(o.tableRight, `${id}: tabela além da borda`).toBeLessThanOrEqual(1);
          expect(o.hidden, `${id}: conteúdo escondido na rolagem horizontal`).toBeLessThanOrEqual(1);
        }
      }
      // Sem vão entre os controles e o resumo: o resumo começa logo abaixo dos controles.
      const gap = await page.evaluate(() => {
        const controls = document.querySelector('[aria-labelledby="pregao-h-controles"]')!.getBoundingClientRect();
        const resumo = document.getElementById("pregao-h-resumo")!.getBoundingClientRect();
        return resumo.top - controls.bottom;
      });
      expect(gap).toBeLessThanOrEqual(24);
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
    // 1h é o padrão (DEFAULT_PREFS): sai dele com "1" para que "2" prove o próprio atalho.
    await page.keyboard.press("1");
    await expect(page.getByTestId("pregao-timeframe").locator('[data-tf="15m"]')).toHaveAttribute("aria-checked", "true");
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
    const canvas = chart.locator("canvas").first();
    await expect(canvas).toBeVisible();
    // Marca o canvas atual: um gráfico recriado traz canvas novos (mesma contagem), sem a marca.
    await canvas.evaluate((el) => {
      (el as HTMLElement).dataset.qa = "original";
    });
    await page.getByTestId("pregao-timeframe").locator('[data-tf="1d"]').click();
    await expect(chart).toHaveAttribute("data-tf", "1d");
    await expect(chart).toHaveAttribute("data-state", "ready");
    await expect(chart.locator('canvas[data-qa="original"]')).toHaveCount(1);
    expect(await chart.locator('canvas[data-qa="original"]').evaluate((el) => el.isConnected)).toBe(true);
  });

  test("troca de tema repinta o gráfico com os tokens do tema novo", async ({ page }) => {
    const chart = page.getByTestId("pregao-chart");
    await expect(chart).toHaveAttribute("data-state", "ready");
    await expect(chart.locator("canvas").first()).toBeVisible();
    // Fundo do painel principal (maior canvas, cor majoritária perto do canto) contra `--surface` do <html>.
    const paintedSurface = () =>
      page.evaluate(() => {
        const toRgb = (color: string) => {
          const ctx = document.createElement("canvas").getContext("2d")!;
          ctx.fillStyle = color;
          ctx.fillRect(0, 0, 1, 1);
          const d = ctx.getImageData(0, 0, 1, 1).data;
          return `${d[0]},${d[1]},${d[2]}`;
        };
        const canvases = [...document.querySelectorAll<HTMLCanvasElement>('[data-testid="pregao-chart"] canvas')];
        const main = canvases.sort((a, b) => b.width * b.height - a.width * a.height)[0];
        const ctx = main.getContext("2d")!;
        const votes = new Map<string, number>();
        for (const [fx, fy] of [[0.05, 0.05], [0.1, 0.07], [0.07, 0.12], [0.03, 0.2], [0.12, 0.03]]) {
          const d = ctx.getImageData(Math.floor(main.width * fx), Math.floor(main.height * fy), 1, 1).data;
          const k = `${d[0]},${d[1]},${d[2]}`;
          votes.set(k, (votes.get(k) ?? 0) + 1);
        }
        const bg = [...votes.entries()].sort((a, b) => b[1] - a[1])[0][0];
        const surface = toRgb(getComputedStyle(document.documentElement).getPropertyValue("--surface").trim());
        return bg === surface ? "igual" : `fundo ${bg} ≠ --surface ${surface}`;
      });
    await expect.poll(paintedSurface).toBe("igual");
    const wasDark = await page.evaluate(() => document.documentElement.classList.contains("dark"));
    await page.getByRole("button", { name: /Ativar tema (claro|escuro)/ }).first().click();
    await expect.poll(() => page.evaluate(() => document.documentElement.classList.contains("dark"))).toBe(!wasDark);
    await expect.poll(paintedSurface).toBe("igual");
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

/** §0.13: com movimento reduzido a fita vira lista estática, sem deslocamento nem item cortado (A11Y-1). */
test.describe("Pregão com movimento reduzido", () => {
  test.use({ reducedMotion: "reduce" });

  test("fita parada, sem translate, com todos os itens dentro da caixa", async ({ page }) => {
    await page.goto("/pregao");
    const tape = page.getByTestId("pregao-ticker");
    await expect(tape).toHaveAttribute("data-state", "ready");
    const list = tape.locator("ul");
    const motion = await list.evaluate((el) => {
      const cs = getComputedStyle(el);
      return { name: cs.animationName, transform: cs.transform };
    });
    expect(motion.name).toBe("none");
    expect(motion.transform).toBe("none");
    const box = await tape.boundingBox();
    expect(box).not.toBeNull();
    const items = tape.locator('[data-testid="pregao-ticker-item"]:not([data-dup])');
    const count = await items.count();
    expect(count).toBeGreaterThan(0);
    for (let i = 0; i < count; i++) {
      const b = await items.nth(i).boundingBox();
      expect(b, `item ${i}`).not.toBeNull();
      expect(b!.x, `item ${i} começa dentro da fita`).toBeGreaterThanOrEqual(box!.x - 0.5);
      expect(b!.x + b!.width, `item ${i} termina dentro da fita`).toBeLessThanOrEqual(box!.x + box!.width + 0.5);
    }
    await expect(tape.locator('[data-testid="pregao-ticker-item"][data-dup="true"]').first()).toBeHidden();
  });
});
