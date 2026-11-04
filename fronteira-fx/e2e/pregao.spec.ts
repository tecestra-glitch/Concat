import { expect, test, type Page } from "@playwright/test";

/**
 * Nenhuma tabela do bloco passa da borda dele, nem esconde conteúdo numa rolagem horizontal interna
 * (a rolagem existe só como rede de segurança; um scroller sem pista visual cortaria colunas).
 */
async function expectTablesFit(page: Page, id: string): Promise<void> {
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

/** Borda inferior (px, relativa à página) de um elemento por seletor CSS. */
function bottomOf(page: Page, selector: string): Promise<number> {
  return page.locator(selector).first().evaluate((el) => el.getBoundingClientRect().bottom + window.scrollY);
}
function topOf(page: Page, selector: string): Promise<number> {
  return page.locator(selector).first().evaluate((el) => el.getBoundingClientRect().top + window.scrollY);
}

/**
 * Tela de pregão em modo demo (sem backend), nos 3 projetos (1440 / 1024 / 390).
 * Espera sempre por elementos (`data-testid`, `data-state`); nunca por rede ociosa nem por tempo fixo.
 */
/**
 * O estado do pregão depende do relógio: de madrugada só as digitais estão abertas ("só digitais").
 * Quarta 2026-11-04 às 14:00Z = 11:00 em Assunção (físicas abertas); às 03:45Z = 00:45 (só digitais).
 */
const HORARIO_ABERTO = new Date("2026-11-04T14:00:00Z");
const MADRUGADA = new Date("2026-11-04T03:45:00Z");

test.describe("Pregão", () => {
  test.beforeEach(async ({ page }) => {
    await page.clock.setFixedTime(HORARIO_ABERTO);
    await page.goto("/pregao");
    await expect(page.getByRole("heading", { level: 1, name: "Pregão" })).toBeVisible();
  });

  test("blocos essenciais e sem rolagem horizontal", async ({ page }, info) => {
    const mobile = info.project.name === "mobile-390";
    await expect(page.getByTestId("demo-banner")).toBeVisible();
    // No celular a nota do pregão repetiria a faixa global de demonstração e empurraria as abas para baixo.
    if (mobile) await expect(page.getByTestId("pregao-demo-note")).toBeHidden();
    else await expect(page.getByTestId("pregao-demo-note")).toBeVisible();
    await expect(page.getByTestId("pregao-ticker")).toHaveAttribute("data-state", "ready");
    await expect(page.getByTestId("pregao-ticker-item").first()).toBeVisible();
    await expect(page.getByTestId("pregao-clock")).toBeVisible();
    await expect(page.getByTestId("pregao-market-status")).toBeVisible();
    await expect(page.getByTestId("pregao-stats")).toHaveAttribute("data-state", "ready");
    await expect(page.getByTestId("pregao-chart")).toHaveAttribute("data-state", "ready");
    await expect(page.getByTestId("pregao-chart").locator("canvas").first()).toBeVisible();
    // Logotipo da biblioteca: o link fica (licença), com título em português.
    await expect(page.getByTestId("pregao-chart").locator("a#tv-attr-logo")).toHaveAttribute("title", "Gráfico por TradingView");
    if (mobile) {
      await expect(page.getByTestId("pregao-tabs")).toBeVisible();
      await expect(page.getByTestId("pregao-book")).toBeHidden();
      // Primeira tela: as abas na primeira metade; intervalo e indicadores só na aba Gráfico, o par em todas.
      const tabsTop = await page.getByTestId("pregao-tabs").evaluate((el) => el.getBoundingClientRect().top);
      expect(tabsTop, "abas na primeira metade da tela").toBeLessThan(844 / 2);
      for (const id of ["pregao-timeframe", "pregao-indicators", "pregao-pair"]) await expect(page.getByTestId(id)).toBeVisible();
      await page.getByRole("tab", { name: "Livro" }).click();
      await expect(page.getByTestId("pregao-timeframe")).toBeHidden();
      await expect(page.getByTestId("pregao-indicators")).toBeHidden();
      await expect(page.getByTestId("pregao-pair")).toBeVisible();
      await expect(page.getByTestId("pregao-book")).toBeVisible();
      await expect(page.getByTestId("pregao-heatmap")).toBeVisible();
      await expect(page.getByTestId("pregao-cross")).toBeVisible();
      for (const id of ["pregao-book", "pregao-heatmap"]) await expectTablesFit(page, id);
      await page.screenshot({ path: "dev/screenshots/pregao-mobile-390-livro.png", fullPage: true });
      await page.getByRole("tab", { name: "Lista" }).click();
      await expect(page.getByTestId("pregao-watchlist")).toHaveAttribute("data-state", "ready");
      await expectTablesFit(page, "pregao-watchlist");
      // Mesma casa em duas filiais: a sigla da cidade vem sob o nome (a coluna Cidade some no celular).
      await expect(page.getByTestId("pregao-watchlist").getByTestId("pregao-watchlist-city").first()).toBeVisible();
      await expect(page.getByTestId("pregao-watchlist").getByTestId("pregao-watchlist-status").first()).toBeVisible();
      await page.screenshot({ path: "dev/screenshots/pregao-mobile-390-lista.png", fullPage: true });
      await page.getByRole("tab", { name: "Últimas" }).click();
      await expect(page.getByTestId("pregao-prints")).toBeVisible();
      await expect(page.getByTestId("pregao-print-row").first()).toBeVisible();
      await expectTablesFit(page, "pregao-prints");
      // Sem rolagem dentro da página: a lista inteira entra no fluxo e a última linha não fica cortada.
      const inner = await page.getByTestId("pregao-prints").evaluate((root) => {
        const sc = root.querySelector("table")!.parentElement!;
        return { scrollHeight: sc.scrollHeight, clientHeight: sc.clientHeight, fade: getComputedStyle(root.querySelector('[data-testid="pregao-prints-fade"]')!).display };
      });
      expect(inner.scrollHeight - inner.clientHeight, "rolagem vertical dentro da aba Últimas").toBeLessThanOrEqual(1);
      expect(inner.fade).toBe("none");
      await page.screenshot({ path: "dev/screenshots/pregao-mobile-390-ultimas.png", fullPage: true });
      await page.getByRole("tab", { name: "Gráfico" }).click();
      await expect(page.getByTestId("pregao-chart")).toBeVisible();
    } else {
      await expect(page.getByTestId("pregao-tabs")).toBeHidden();
      for (const id of ["pregao-book", "pregao-heatmap", "pregao-cross", "pregao-prints", "pregao-watchlist"]) await expect(page.getByTestId(id)).toBeVisible();
      // Livro, mapa, últimas e lista cabem no próprio painel: nenhuma tabela passa da borda do painel (nem com rolagem interna).
      await expect(page.getByTestId("pregao-print-row").first()).toBeVisible();
      await expect(page.getByTestId("pregao-watchlist")).toHaveAttribute("data-state", "ready");
      for (const id of ["pregao-book", "pregao-heatmap", "pregao-prints", "pregao-watchlist"]) await expectTablesFit(page, id);
      // Compra e Venda empilhadas no livro: mesmas colunas (x e largura de cada cabeçalho) e nomes de casa sem corte.
      const sides = await page.getByTestId("pregao-book").evaluate((root) => {
        const heads = (side: string) =>
          [...root.querySelectorAll(`[data-testid="pregao-book-side-${side}"] thead th`)].map((th) => {
            const r = th.getBoundingClientRect();
            return [Math.round(r.left), Math.round(r.width), Math.round(r.height)];
          });
        const spill = [...root.querySelectorAll<HTMLElement>('[data-testid="pregao-book-row"] td')].filter((td) => td.scrollWidth > td.clientWidth + 1).map((td) => td.textContent);
        const cut = [...root.querySelectorAll<HTMLElement>('[data-testid="pregao-book-row"] .truncate')].filter((el) => el.scrollWidth > el.clientWidth + 1).map((el) => el.textContent);
        return { buy: heads("buy"), sell: heads("sell"), cut, spill };
      });
      expect(sides.sell).toEqual(sides.buy);
      expect(sides.cut, "nomes cortados no livro").toEqual([]);
      expect(sides.spill, "conteúdo invadindo a coluna vizinha no livro").toEqual([]);
      // Idade ("5 min") com folga antes do anel da linha selecionada (ring-1 inset): o "n" não encosta nele.
      const ageGap = await page.getByTestId("pregao-book").evaluate((root) =>
        [...root.querySelectorAll<HTMLElement>('[data-testid="pregao-book-row"] td:last-child span[aria-hidden="true"]')].map((span) => {
          const row = span.closest("tr")!.getBoundingClientRect();
          return Math.round((row.right - span.getBoundingClientRect().right) * 10) / 10;
        }),
      );
      expect(ageGap.length).toBeGreaterThan(0);
      expect(Math.min(...ageGap), "idade encostada na borda da linha").toBeGreaterThanOrEqual(3);
      // Últimas atualizações: o selo "incompleta" nunca reduz o nome da casa a "No…".
      const cutNames = await page.getByTestId("pregao-prints").evaluate((root) =>
        [...root.querySelectorAll<HTMLElement>('[data-testid="pregao-print-row"] td:nth-child(2) .truncate')]
          .filter((el) => el.offsetParent !== null && el.closest("td")!.textContent!.includes("incompleta") && el.scrollWidth > el.clientWidth + 1)
          .map((el) => el.textContent),
      );
      expect(cutNames, "nome cortado ao lado do selo incompleta").toEqual([]);
      // Sem vão entre os controles e o resumo: o resumo começa logo abaixo dos controles.
      const gap = await page.evaluate(() => {
        const controls = document.querySelector('[aria-labelledby="pregao-h-controles"]')!.getBoundingClientRect();
        const resumo = document.getElementById("pregao-h-resumo")!.getBoundingClientRect();
        return resumo.top - controls.bottom;
      });
      expect(gap).toBeLessThanOrEqual(24);
      // Sem vão ao lado do livro: a coluna da esquerda (gráfico + mapa + cruzado) termina perto do fim do livro,
      // o mapa começa logo abaixo do gráfico, e o que vem depois começa logo abaixo da coluna mais alta.
      const chartBottom = await bottomOf(page, "#pregao-panel-grafico");
      const extraTop = await topOf(page, "#pregao-panel-livro-extra");
      const leftBottom = await bottomOf(page, "#pregao-panel-livro-extra");
      const bookBottom = await bottomOf(page, "#pregao-panel-livro");
      expect(extraTop - chartBottom, "vão entre o gráfico e o mapa").toBeLessThanOrEqual(24);
      expect(Math.abs(leftBottom - bookBottom), "coluna do gráfico × fim do livro").toBeLessThanOrEqual(200);
      const tallest = Math.max(leftBottom, bookBottom);
      if (info.project.name === "desktop-1440") {
        // xl: "Últimas" vai da sessão até o fim da grade (sem teto de 22rem) e a lista vem logo depois.
        const printsBottom = await bottomOf(page, "#pregao-panel-ultimas");
        expect(Math.abs(printsBottom - tallest), "coluna das últimas × coluna mais alta").toBeLessThanOrEqual(24);
        expect((await topOf(page, "#pregao-panel-lista")) - printsBottom, "vão antes da lista").toBeLessThanOrEqual(40);
        // Aqui a lista rola por dentro do painel: se houver mais linhas que a altura, o degradê avisa e fica colado à borda de baixo.
        const xlFade = await page.getByTestId("pregao-prints").evaluate((root) => {
          const sc = root.querySelector("table")!.parentElement!;
          const box = sc.getBoundingClientRect();
          const f = root.querySelector('[data-testid="pregao-prints-fade"]')!.getBoundingClientRect();
          return { overflow: sc.scrollHeight > sc.clientHeight + 1, gap: Math.abs(box.bottom - f.bottom), height: f.height };
        });
        if (xlFade.overflow) {
          expect(xlFade.height, "degradê visível quando a lista continua").toBeGreaterThan(0);
          expect(xlFade.gap).toBeLessThanOrEqual(1);
        }
      } else {
        // lg: "Últimas" ocupa as duas colunas logo abaixo da mais alta.
        expect((await topOf(page, "#pregao-panel-ultimas")) - tallest, "vão antes das últimas").toBeLessThanOrEqual(40);
        // Teto de 22rem: a linha cortada ao meio no rodapé ganha um degradê colado à borda de baixo do scroller.
        const fade = await page.getByTestId("pregao-prints").evaluate((root) => {
          const sc = root.querySelector("table")!.parentElement!.getBoundingClientRect();
          const f = root.querySelector('[data-testid="pregao-prints-fade"]')!.getBoundingClientRect();
          return { gap: Math.abs(sc.bottom - f.bottom), height: f.height };
        });
        expect(fade.height).toBeGreaterThan(0);
        expect(fade.gap).toBeLessThanOrEqual(1);
      }
    }
    const { scrollWidth, clientWidth } = await page.evaluate(() => ({ scrollWidth: document.documentElement.scrollWidth, clientWidth: document.documentElement.clientWidth }));
    expect(scrollWidth).toBeLessThanOrEqual(clientWidth + 1);
    await page.screenshot({ path: `dev/screenshots/pregao-${info.project.name}.png`, fullPage: true });
  });

  test("abas do celular grudam abaixo do cabeçalho do app ao rolar", async ({ page }) => {
    test.skip(test.info().project.name !== "mobile-390", "abas só existem abaixo de md");
    await page.getByRole("tab", { name: "Livro" }).click();
    await expect(page.getByTestId("pregao-book")).toHaveAttribute("data-state", "ready");
    await page.evaluate(() => window.scrollTo(0, 1500));
    await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThan(1000);
    const pos = await page.evaluate(() => {
      const header = document.querySelector("header")!.getBoundingClientRect();
      const tabs = document.querySelector('[data-testid="pregao-tabs"]')!;
      const r = tabs.getBoundingClientRect();
      const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
      return { headerBottom: header.bottom, tabsTop: r.top, onTop: hit !== null && tabs.contains(hit) };
    });
    expect(pos.tabsTop, "abas abaixo do cabeçalho").toBeGreaterThanOrEqual(pos.headerBottom - 0.5);
    expect(pos.tabsTop, "abas grudadas no topo da área visível").toBeLessThanOrEqual(pos.headerBottom + 8);
    expect(pos.onTop, "abas visíveis, não cobertas pelo cabeçalho").toBe(true);
    // Troca de aba dali mesmo, sem voltar ao topo.
    await page.getByRole("tab", { name: "Lista" }).click();
    await expect(page.getByRole("tab", { name: "Lista" })).toHaveAttribute("aria-selected", "true");
    await expect(page.getByTestId("pregao-watchlist")).toBeVisible();
  });

  test("foco por teclado no livro não fica atrás do cabeçalho, das abas nem da barra inferior (WCAG 2.4.11)", async ({ page }) => {
    test.skip(test.info().project.name !== "mobile-390", "abas grudadas e barra inferior só existem no celular");
    await page.getByRole("tab", { name: "Livro" }).click();
    await expect(page.getByTestId("pregao-book")).toHaveAttribute("data-state", "ready");
    const rows = page.getByTestId("pregao-book-row");
    const n = await rows.count();
    expect(n).toBeGreaterThan(3);
    await rows.nth(n - 1).focus();
    let checked = 0;
    for (let i = 0; i < Math.min(n - 1, 10); i++) {
      await page.keyboard.press("Shift+Tab");
      const r = await page.evaluate(() => {
        const el = document.activeElement as HTMLElement;
        const tabs = document.querySelector('[data-testid="pregao-tabs"]')!.getBoundingClientRect();
        const nav = document.querySelector('[data-testid="mobile-nav"]')!.getBoundingClientRect();
        const b = el.getBoundingClientRect();
        return { row: el.dataset.testid === "pregao-book-row", top: b.top, bottom: b.bottom, tabsBottom: tabs.bottom, navTop: nav.top };
      });
      if (!r.row) continue;
      checked += 1;
      expect(r.top, "linha focada abaixo das abas").toBeGreaterThanOrEqual(r.tabsBottom - 1);
      expect(r.bottom, "linha focada acima da barra inferior").toBeLessThanOrEqual(r.navTop + 1);
    }
    expect(checked, "linhas do livro percorridas com Shift+Tab").toBeGreaterThan(2);
  });

  test("fita estática: sem animação, sem botão de pausa, rolagem horizontal manual", async ({ page }) => {
    const tape = page.getByTestId("pregao-ticker");
    await expect(tape).toHaveAttribute("data-state", "ready");
    await expect(tape.getByRole("button", { name: "Pausar fita" })).toHaveCount(0);
    await expect(page.getByTestId("pregao-ticker-scroll")).toHaveCSS("overflow-x", "auto");
    const name = await tape.locator("ul").evaluate((el) => getComputedStyle(el).animationName);
    expect(name).toBe("none");
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
    await page.getByRole("button", { name: "Alternar tema" }).first().click();
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

test.describe("Pregão de madrugada (só digitais)", () => {
  test("blocos essenciais e sem rolagem horizontal às 03:45Z", async ({ page }, info) => {
    await page.clock.setFixedTime(MADRUGADA);
    await page.goto("/pregao");
    await expect(page.getByRole("heading", { level: 2, name: "Pregão" })).toBeVisible();
    const mobile = info.project.name === "mobile-390";
    await expect(page.getByTestId("pregao-ticker")).toHaveAttribute("data-state", "ready");
    await expect(page.getByTestId("pregao-clock")).toBeVisible();
    await expect(page.getByTestId("pregao-market-status")).toBeVisible();
    await expect(page.getByTestId("pregao-stats")).toHaveAttribute("data-state", "ready");
    await expect(page.getByTestId("pregao-chart")).toHaveAttribute("data-state", "ready");
    await expect(page.getByTestId("pregao-chart").locator("canvas").first()).toBeVisible();
    if (mobile) {
      for (const [tab, id] of [["Livro", "pregao-book"], ["Lista", "pregao-watchlist"], ["Últimas", "pregao-prints"]] as const) {
        await page.getByRole("tab", { name: tab }).click();
        await expect(page.getByTestId(id)).toBeVisible();
        await expectTablesFit(page, id);
      }
    } else {
      await expect(page.getByTestId("pregao-book")).toBeVisible();
      await expect(page.getByTestId("pregao-prints")).toBeVisible();
      await expect(page.getByTestId("pregao-watchlist")).toBeVisible();
      for (const id of ["pregao-book", "pregao-prints", "pregao-watchlist"]) await expectTablesFit(page, id);
    }
    const { scrollWidth, clientWidth } = await page.evaluate(() => ({ scrollWidth: document.documentElement.scrollWidth, clientWidth: document.documentElement.clientWidth }));
    expect(scrollWidth, "rolagem horizontal da página às 03:45Z").toBeLessThanOrEqual(clientWidth + 1);
    await page.screenshot({ path: `dev/screenshots/pregao-madrugada-${info.project.name}.png`, fullPage: true });
  });
});

/** §0.13: com movimento reduzido a fita vira lista estática, sem deslocamento nem item cortado (A11Y-1). */
test.describe("Pregão com movimento reduzido", () => {
  test.use({ reducedMotion: "reduce" });

  test("fita sem movimento: sem animação, sem transform, rolagem manual", async ({ page }) => {
    await page.goto("/pregao");
    const tape = page.getByTestId("pregao-ticker");
    await expect(tape).toHaveAttribute("data-state", "ready");
    const motion = await tape.locator("ul").evaluate((el) => {
      const cs = getComputedStyle(el);
      return { name: cs.animationName, transform: cs.transform };
    });
    expect(motion.name).toBe("none");
    expect(motion.transform).toBe("none");
    await expect(page.getByTestId("pregao-ticker-scroll")).toHaveCSS("overflow-x", "auto");
  });
});
