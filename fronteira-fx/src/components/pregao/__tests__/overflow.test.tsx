import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { BookLadder } from "@/components/pregao/book-ladder";
import { LatestPrints } from "@/components/pregao/latest-prints";
import { SpreadHeatmap } from "@/components/pregao/spread-heatmap";
import { StatsStrip } from "@/components/pregao/stats-strip";
import { demoBook, demoHeat, demoPrints, demoStats } from "@/lib/pregao/demo";

/**
 * Regressões achadas na montagem (e2e "sem rolagem horizontal" em 1440 e 1024 px):
 * - texto `sr-only` é `position: absolute`; dentro de um contêiner com rolagem que não é posicionado,
 *   ele escapa do recorte e alarga a página. Todo contêiner com rolagem leva `relative`, como o
 *   `Table` de `src/components/ui/table.tsx`;
 * - o livro mora numa coluna de 20rem em `lg+`: os dois lados lado a lado dependem da largura do
 *   próprio bloco (consulta de contêiner), não da largura da janela.
 */
const NOW = new Date(Date.UTC(2026, 10, 2, 12, 0));
const noop = () => {};

function scrollerClasses(html: string): string[][] {
  return [...html.matchAll(/class="([^"]*\boverflow-(?:x|y)?-?(?:auto|scroll)\b[^"]*)"/g)].map((m) => m[1].split(" "));
}

describe("contêineres com rolagem recortam o texto para leitor de tela", () => {
  it("Últimas atualizações", () => {
    const html = renderToStaticMarkup(<LatestPrints prints={demoPrints(NOW, 30)} onSelect={noop} />);
    expect(html).toContain('data-state="ready"');
    const scrollers = scrollerClasses(html);
    expect(scrollers.length).toBeGreaterThan(0);
    for (const c of scrollers) expect(c, c.join(" ")).toContain("relative");
  });

  it("Mapa de spread", () => {
    const cells = demoHeat(NOW);
    const houses = [...new Map(cells.map((c) => [c.source_id, { source_id: c.source_id, house: c.house }])).values()];
    const html = renderToStaticMarkup(<SpreadHeatmap cells={cells} houses={houses} selectedKey={null} onSelect={noop} />);
    expect(html).toContain('data-state="ready"');
    const scrollers = scrollerClasses(html);
    expect(scrollers.length).toBeGreaterThan(0);
    for (const c of scrollers) expect(c, c.join(" ")).toContain("relative");
  });
});

describe("livro de casas na coluna estreita", () => {
  it("lados lado a lado só quando o próprio bloco é largo (@container), nunca pela largura da janela", () => {
    const html = renderToStaticMarkup(<BookLadder levels={demoBook("USD/PYG", NOW)} pair="USD/PYG" quote="PYG" selectedKey={null} onSelect={noop} now={NOW.getTime()} />);
    expect(html).toMatch(/data-testid="pregao-book"[^>]*class="[^"]*@container/);
    expect(html).toContain("@md:grid-cols-2");
    expect(html).not.toMatch(/\bsm:grid-cols-2\b/);
  });
});

describe("resumo da sessão na coluna do gráfico", () => {
  const stats = demoStats("chaco:CDE:USD/PYG:cash:@chaco-cde-centro", NOW);

  it("colunas pela largura do próprio bloco (@container), nunca 8 colunas pela largura da janela", () => {
    const html = renderToStaticMarkup(<StatsStrip stats={stats} quote="PYG" now={NOW.getTime()} />);
    expect(html).toMatch(/data-testid="pregao-stats"[^>]*class="[^"]*@container/);
    expect(html).toContain("@lg:grid-cols-4");
    expect(html).not.toMatch(/\b(sm|xl):grid-cols-/);
  });

  it("dl só com grupos dt/dd (axe definition-list); o corte diário fica fora da lista", () => {
    const html = renderToStaticMarkup(<StatsStrip stats={stats} quote="PYG" now={NOW.getTime()} />);
    const dl = html.slice(html.indexOf("<dl"), html.indexOf("</dl>"));
    expect(dl).not.toContain("corte diário");
    expect(html).toContain("corte diário 00:00 Assunção");
    expect((dl.match(/<dt/g) ?? []).length).toBe(8);
    for (const state of [{ loading: true }, { error: new Error("falhou") }, { stats: { ...stats, n_quotes: 0 } }]) {
      const other = renderToStaticMarkup(<StatsStrip stats={stats} quote="PYG" now={NOW.getTime()} {...state} />);
      expect(other, JSON.stringify(state)).not.toContain("<dl");
    }
  });
});
