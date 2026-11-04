import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

/**
 * Contrato do CSS do terminal (dev/ui/spec-reforma-ui.md, §3.4 e §6.2): movimento reduzido é obrigatório e precisa
 * parar repetições (iteração 1, nada infinito), esconder o realce e o brilho, e deixar o giro estático.
 */
const CSS = readFileSync(new URL("../app/globals.css", import.meta.url), "utf8");

function block(start: string): string {
  const i = CSS.indexOf(start);
  expect(i, start).toBeGreaterThanOrEqual(0);
  return CSS.slice(i, CSS.indexOf("\n}", i));
}

describe("globals.css: movimento reduzido", () => {
  const reduced = block("@media (prefers-reduced-motion: reduce)");

  it("zera a duração e limita as iterações a 1 (corrige o pulso infinito, A1)", () => {
    expect(reduced).toContain("animation-iteration-count: 1 !important");
    expect(reduced).toContain("animation-duration: 1ms !important");
    expect(reduced).toContain("transition-duration: 1ms !important");
  });

  it("desliga o realce de fluxo (sentido, normal e alternado), o brilho e o giro", () => {
    for (const cls of [".fx-flash-up", ".fx-flash-down", ".fx-flash-up-b", ".fx-flash-down-b", ".fx-skeleton", ".fx-spin"]) {
      expect(reduced, cls).toContain(cls);
    }
    expect(reduced).toMatch(/\.fx-skeleton\s*\{[^}]*animation:\s*none !important/);
  });

  it("o brilho do esqueleto fica estático com a cor base em movimento reduzido", () => {
    expect(reduced).toMatch(/\.fx-skeleton\s*\{[^}]*background:\s*var\(--surface-2\)/);
  });
});

describe("globals.css: tokens e utilitários do terminal", () => {
  it("define os tokens de cor nos dois temas e o escuro como padrão (.dark)", () => {
    const root = block(":root {");
    const dark = block(".dark {");
    for (const v of ["--background", "--surface", "--control-border", "--gain-soft", "--demo", "--ring"]) {
      expect(root, `:root ${v}`).toContain(`${v}:`);
      expect(dark, `.dark ${v}`).toContain(`${v}:`);
    }
  });

  it("raios e movimento vêm de tokens; o antigo --radius saiu", () => {
    expect(CSS).not.toMatch(/--radius:\s*0\.5rem/);
    expect(CSS).toContain("--r-control: 8px");
    expect(CSS).toContain("--motion-base: 200ms");
  });

  it("tem as classes de movimento da spec (fx-enter, fx-skeleton, fx-grid, fx-num)", () => {
    for (const cls of [".fx-enter", ".fx-skeleton", ".fx-grid", ".fx-num", ".fx-segmented-indicator", ".fx-card"]) {
      expect(CSS, cls).toContain(cls);
    }
  });
});
