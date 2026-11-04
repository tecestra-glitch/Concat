import { expect, test } from "@playwright/test";

/**
 * G5 (dev/ui/spec-reforma-ui.md §5b): em 390 px, todo `button`, `a` e `[role=tab]` visível tem caixa de pelo menos
 * 44 × 44, ou de pelo menos 24 × 24 com padding. Exceções: o link "Ir para o conteúdo" (oculto até receber foco) e
 * o interruptor (`role=switch`), cuja área de toque de 44 px vem de um pseudo-elemento (switch.tsx), não da caixa, e o
 * logotipo de atribuição do gráfico (`#tv-attr-logo`), exigido pela licença da biblioteca.
 * Espera sempre por elementos; nunca por rede ociosa.
 */
const ROUTES = ["/", "/pregao", "/mercados", "/oportunidades", "/fontes", "/alertas"];
const SELECTOR = 'button, a[href], [role="tab"], [role="radio"], [role="checkbox"]';

test.describe("alvos de toque (G5)", () => {
  for (const route of ROUTES) {
    test(`alvos de 44 px em ${route}`, async ({ page }) => {
      test.skip(test.info().project.name !== "mobile-390", "alvos de toque medidos só em 390 px");
      await page.goto(route);
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
      const small = await page.evaluate((selector) => {
        const out: string[] = [];
        for (const el of document.querySelectorAll<HTMLElement>(selector)) {
          if (el.classList.contains("sr-only") || el.closest(".sr-only")) continue;
          if (el.getAttribute("role") === "switch") continue; // área de 44 px no pseudo-elemento (switch.tsx)
          if (el.id === "tv-attr-logo") continue; // logotipo de licença da biblioteca de gráfico (fixo, não é controle)
          const cs = getComputedStyle(el);
          if (cs.display === "none" || cs.visibility === "hidden") continue;
          const b = el.getBoundingClientRect();
          if (b.width === 0 || b.height === 0) continue;
          const pad = (v: string) => parseFloat(v) || 0;
          const padX = pad(cs.paddingLeft) + pad(cs.paddingRight);
          const padY = pad(cs.paddingTop) + pad(cs.paddingBottom);
          const ok = (b.width >= 44 && b.height >= 44) || (b.width >= 24 && b.height >= 24 && padX + padY > 0);
          if (!ok) out.push(`${(el.textContent || el.getAttribute("aria-label") || el.tagName).trim().slice(0, 40)} ${Math.round(b.width)}x${Math.round(b.height)}`);
        }
        return out;
      }, SELECTOR);
      expect(small, `${route}: alvos menores que o mínimo`).toEqual([]);
    });
  }
});
