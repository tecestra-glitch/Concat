import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { TOKEN_VARS } from "@/components/pregao/candle-chart-options";

/** Tokens e keyframes do pregão em `src/app/globals.css` (§0.13, §24.2), nos dois temas. */
const CSS = readFileSync(new URL("../../../app/globals.css", import.meta.url).pathname, "utf8");

function block(selector: string): string {
  const start = CSS.indexOf(`${selector} {`);
  expect(start, `bloco ${selector}`).toBeGreaterThanOrEqual(0);
  return CSS.slice(start, CSS.indexOf("\n}", start));
}

function vars(selector: string): Map<string, string> {
  const out = new Map<string, string>();
  for (const m of block(selector).matchAll(/(--[\w-]+):\s*([^;]+);/g)) out.set(m[1], m[2].trim());
  return out;
}

// WCAG 2 (mesma fórmula de dev/contrast-check.mjs).
const lum = (hex: string) => {
  const [r, g, b] = [1, 3, 5]
    .map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
};
const ratio = (fg: string, bg: string) => {
  const [a, b] = [lum(fg), lum(bg)];
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
};

const light = vars(":root");
const dark = vars(".dark");
const HEAT = ["--heat-1", "--heat-2", "--heat-3", "--heat-4", "--heat-5"];
const CHART = ["--chart-grid", "--chart-volume", "--chart-sma", "--chart-ema", "--chart-band", "--chart-watermark"];

describe("tokens do pregão em globals.css", () => {
  it("cada variável que o gráfico lê existe nos dois temas (sem cair no fallback)", () => {
    const fromTheme = Object.values(TOKEN_VARS).filter((v) => v !== "--font-mono");
    for (const v of fromTheme) {
      expect(light.has(v), `:root ${v}`).toBe(true);
      expect(dark.has(v), `.dark ${v}`).toBe(true);
    }
    expect(CSS).toMatch(/--font-mono:/);
  });

  it("mapa de calor e séries do gráfico nos dois temas; superfícies extras no @theme", () => {
    for (const v of [...HEAT, ...CHART, "--border-strong", "--surface-3"]) {
      expect(light.has(v), `:root ${v}`).toBe(true);
      expect(dark.has(v), `.dark ${v}`).toBe(true);
    }
    const theme = block("@theme inline");
    expect(theme).toContain("--color-border-strong: var(--border-strong);");
    expect(theme).toContain("--color-surface-3: var(--surface-3);");
  });

  it("mapa de calor: um só matiz, luminância decrescendo do passo 1 ao 5 no claro e crescendo no escuro", () => {
    const l = HEAT.map((v) => lum(light.get(v)!));
    const d = HEAT.map((v) => lum(dark.get(v)!));
    for (let i = 1; i < 5; i++) {
      expect(l[i]).toBeLessThan(l[i - 1]);
      expect(d[i]).toBeGreaterThan(d[i - 1]);
    }
  });

  it("contraste WCAG AA dos pares de §0.13", () => {
    const pairs: [Map<string, string>, string, string, number][] = [
      [light, "--gain", "--surface", 4.5],
      [light, "--gain", "--surface-2", 4.5],
      [light, "--loss", "--surface", 4.5],
      [light, "--loss", "--surface-2", 4.5],
      [light, "--warn", "--surface", 4.5],
      [light, "--foreground", "--heat-1", 4.5],
      [light, "--foreground", "--heat-5", 4.5],
      [light, "--chart-sma", "--surface", 3],
      [light, "--chart-ema", "--surface", 3],
      [light, "--chart-band", "--surface", 3],
      [dark, "--gain", "--surface", 4.5],
      [dark, "--loss", "--surface", 4.5],
      [dark, "--warn", "--surface", 4.5],
      [dark, "--foreground", "--heat-1", 4.5],
      [dark, "--foreground", "--heat-5", 4.5],
      [dark, "--chart-sma", "--surface", 3],
      [dark, "--chart-ema", "--surface", 3],
      [dark, "--chart-band", "--surface", 3],
    ];
    for (const [theme, fg, bg, min] of pairs) {
      const r = ratio(theme.get(fg)!, theme.get(bg)!);
      expect(r, `${theme === light ? "claro" : "escuro"} ${fg} sobre ${bg}`).toBeGreaterThanOrEqual(min);
    }
  });

  it("selos gain/accent: texto -strong sobre o próprio matiz a 15 % passa 4,5:1 nos dois temas", () => {
    // Mistura em sRGB (o Tailwind mistura em oklab; a diferença não muda a conclusão com esta folga).
    const mix = (fg: string, bg: string, a: number) =>
      "#" +
      [1, 3, 5]
        .map((i) => Math.round(parseInt(fg.slice(i, i + 2), 16) * a + parseInt(bg.slice(i, i + 2), 16) * (1 - a)))
        .map((n) => n.toString(16).padStart(2, "0"))
        .join("");
    for (const theme of [light, dark]) {
      for (const [text, hue] of [["--gain-strong", "--gain"], ["--accent-strong", "--accent"]]) {
        for (const base of ["--background", "--surface", "--surface-2"]) {
          const bg = mix(theme.get(hue)!, theme.get(base)!, 0.15);
          const r = ratio(theme.get(text)!, bg);
          expect(r, `${theme === light ? "claro" : "escuro"} ${text} sobre ${hue}/15 em ${base}`).toBeGreaterThanOrEqual(4.5);
        }
      }
    }
    const theme = block("@theme inline");
    expect(theme).toContain("--color-gain-strong: var(--gain-strong);");
    expect(theme).toContain("--color-accent-strong: var(--accent-strong);");
  });

  it("keyframes da fita e do destaque; a fita pausa em hover e foco", () => {
    expect(CSS).toMatch(/@keyframes pregao-marquee\s*\{[^}]*translateX\(0\)[^}]*\}[^}]*translateX\(-50%\)/);
    expect(CSS).toMatch(/\.pregao-marquee\s*\{[^}]*animation:\s*pregao-marquee var\(--tape-duration, 40s\) linear infinite;/);
    expect(CSS).toMatch(/\.pregao-marquee:hover,\s*\.pregao-marquee:focus-within\s*\{[^}]*animation-play-state:\s*paused;/);
    expect(CSS).toMatch(/@keyframes pregao-flash\s*\{[^}]*var\(--surface-2\)[^}]*\}[^}]*transparent/);
  });
});
