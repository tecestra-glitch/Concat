import { readFileSync } from "node:fs";
import type { ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { MOBILE_TABS, PregaoLayout, nextTab, type PregaoLayoutProps } from "../pregao-layout";

const SLOT_NAMES = ["banner", "ticker", "controls", "stats", "chart", "book", "bookExtra", "prints", "watchlist", "clocks"] as const;

function slotNodes(): Record<(typeof SLOT_NAMES)[number], ReactNode> {
  return {
    banner: <div data-testid="slot-banner" />,
    ticker: <div data-testid="slot-ticker" />,
    controls: <div data-testid="slot-controls" />,
    stats: <div data-testid="slot-stats" />,
    chart: <div data-testid="slot-chart" />,
    book: <div data-testid="slot-book" />,
    bookExtra: <div data-testid="slot-bookExtra" />,
    prints: <div data-testid="slot-prints" />,
    watchlist: <div data-testid="slot-watchlist" />,
    clocks: <div data-testid="slot-clocks" />,
  };
}

function render(extra: Partial<PregaoLayoutProps> = {}): string {
  const props: PregaoLayoutProps = { ...slotNodes(), ...extra };
  return renderToStaticMarkup(<PregaoLayout {...props} />);
}

/** Abre a tag (de qualquer elemento) que contém o atributo informado, ex.: `data-testid="pregao-tabs"`. */
function tagWith(html: string, attr: string): string {
  const match = html.match(new RegExp(`<[a-zA-Z0-9]+\\s(?:[^>]*\\s)?${attr}[\\s>][^>]*>`));
  if (!match) throw new Error(`elemento não encontrado: ${attr}`);
  return match[0];
}

function classesOf(tag: string): string[] {
  const match = tag.match(/\sclass="([^"]*)"/);
  return match ? match[1].split(/\s+/).filter(Boolean) : [];
}

function tabTag(html: string, id: PregaoLayoutProps["defaultTab"] & string): string {
  return tagWith(html, `id="pregao-tab-${id}"`);
}

describe("PregaoLayout — slots", () => {
  it("renderiza os 10 slots", () => {
    const html = render();
    for (const name of SLOT_NAMES) {
      expect(html).toContain(`data-testid="slot-${name}"`);
    }
    expect(html.match(/data-testid="slot-/g)?.length).toBe(10);
  });

  it("envolve o banner em pregao-banner", () => {
    const html = render();
    expect(html).toMatch(/data-testid="pregao-banner">\s*<div data-testid="slot-banner"/);
  });

  it("sem banner (null) não renderiza pregao-banner e mantém os demais slots", () => {
    const html = render({ banner: null });
    expect(html).not.toContain("pregao-banner");
    expect(html).toContain('data-testid="slot-ticker"');
    expect(html).toContain('data-testid="slot-clocks"');
  });
});

describe("PregaoLayout — abas do celular", () => {
  it("MOBILE_TABS lista as quatro abas na ordem e com os rótulos exatos", () => {
    expect(MOBILE_TABS.map((t) => t.id)).toEqual(["grafico", "livro", "lista", "ultimas"]);
    expect(MOBILE_TABS.map((t) => t.label)).toEqual(["Gráfico", "Livro", "Lista", "Últimas"]);
  });

  it("renderiza quatro role=tab com id e aria-controls correspondentes", () => {
    const html = render();
    expect(html.match(/role="tab"/g)?.length).toBe(4);
    for (const id of ["grafico", "lista", "ultimas"] as const) {
      const tag = tabTag(html, id);
      expect(tag).toContain(`aria-controls="pregao-panel-${id}"`);
      expect(tag).toContain('role="tab"');
    }
    // A aba Livro controla o livro e o bloco do mapa + cruzado (que em lg+ mora sob o gráfico).
    expect(tabTag(html, "livro")).toContain('aria-controls="pregao-panel-livro pregao-panel-livro-extra"');
  });

  it("por padrão só Gráfico está selecionada e é a única com tabIndex 0", () => {
    const html = render();
    expect(tabTag(html, "grafico")).toContain('aria-selected="true"');
    expect(tabTag(html, "grafico")).toContain('tabindex="0"');
    for (const id of ["livro", "lista", "ultimas"] as const) {
      expect(tabTag(html, id)).toContain('aria-selected="false"');
      expect(tabTag(html, id)).toContain('tabindex="-1"');
    }
    expect(html).toMatch(/<button[^>]*>Gráfico<\/button>/);
    expect(html).toMatch(/<button[^>]*>Livro<\/button>/);
    expect(html).toMatch(/<button[^>]*>Lista<\/button>/);
    expect(html).toMatch(/<button[^>]*>Últimas<\/button>/);
  });

  it("defaultTab=livro seleciona Livro e marca a raiz com data-mobile-tab", () => {
    const html = render({ defaultTab: "livro" });
    expect(tagWith(html, 'data-testid="pregao-layout"')).toContain('data-mobile-tab="livro"');
    expect(tabTag(html, "livro")).toContain('aria-selected="true"');
    expect(tabTag(html, "grafico")).toContain('aria-selected="false"');
  });

  it("sem defaultTab a raiz começa em grafico", () => {
    const html = render();
    expect(tagWith(html, 'data-testid="pregao-layout"')).toContain('data-mobile-tab="grafico"');
  });
});

describe("PregaoLayout — painéis", () => {
  it("painéis não ativos têm max-md:hidden; o ativo não tem", () => {
    const html = render({ defaultTab: "livro" });
    expect(classesOf(tagWith(html, 'id="pregao-panel-livro"'))).not.toContain("max-md:hidden");
    expect(classesOf(tagWith(html, 'id="pregao-panel-grafico"'))).toContain("max-md:hidden");
    expect(classesOf(tagWith(html, 'id="pregao-panel-lista"'))).toContain("max-md:hidden");
    expect(classesOf(tagWith(html, 'id="pregao-panel-ultimas"'))).toContain("max-md:hidden");
  });

  it("com Gráfico ativa, o painel do gráfico não tem max-md:hidden", () => {
    const html = render();
    expect(classesOf(tagWith(html, 'id="pregao-panel-grafico"'))).not.toContain("max-md:hidden");
    expect(classesOf(tagWith(html, 'id="pregao-panel-livro"'))).toContain("max-md:hidden");
  });

  it("pregao-panel-grafico contém os slots stats e chart", () => {
    const html = render();
    const start = html.indexOf('id="pregao-panel-grafico"');
    const end = html.indexOf('id="pregao-panel-livro"');
    expect(start).toBeGreaterThan(-1);
    expect(end).toBeGreaterThan(start);
    const panel = html.slice(start, end);
    expect(panel).toContain('data-testid="slot-stats"');
    expect(panel).toContain('data-testid="slot-chart"');
  });

  it("em lg+ a sessão ocupa as linhas 1–2 da direita e o gráfico começa na linha 2: a esquerda não herda a altura da sessão", () => {
    const html = render();
    const sessao = classesOf(tagWith(html, 'aria-labelledby="pregao-h-sessao"'));
    expect(sessao).toEqual(expect.arrayContaining(["lg:row-start-1", "lg:row-span-2", "lg:col-start-2", "max-lg:order-first"]));
    const controles = classesOf(tagWith(html, 'aria-labelledby="pregao-h-controles"'));
    expect(controles).toEqual(expect.arrayContaining(["lg:row-start-1", "lg:col-start-1", "xl:col-end-3"]));
    const grafico = classesOf(tagWith(html, 'id="pregao-panel-grafico"'));
    expect(grafico).toEqual(expect.arrayContaining(["lg:row-start-2", "lg:row-span-2", "xl:row-span-1"]));
    const livro = classesOf(tagWith(html, 'id="pregao-panel-livro"'));
    expect(livro).toEqual(expect.arrayContaining(["lg:col-start-2", "lg:row-start-3", "lg:row-span-2", "xl:row-start-2"]));
    // controles, sessão, abas e painéis na mesma grade, com a linha 1fr que absorve a altura do livro
    const grade = tagWith(html, 'data-testid="pregao-tabs"');
    expect(html.indexOf("lg:grid-rows-[auto_auto_1fr_auto_auto]")).toBeLessThan(html.indexOf(grade));
    expect(html).toContain("xl:grid-rows-[auto_auto_1fr]");
    expect(html).toContain("lg:items-start");
  });

  it("mapa + cruzado ficam sob o gráfico em lg+ e escondidos fora da aba Livro no celular", () => {
    const extra = classesOf(tagWith(render(), 'id="pregao-panel-livro-extra"'));
    expect(extra).toEqual(expect.arrayContaining(["lg:col-start-1", "lg:row-start-4", "xl:row-start-3", "max-md:hidden"]));
    expect(classesOf(tagWith(render({ defaultTab: "livro" }), 'id="pregao-panel-livro-extra"'))).not.toContain("max-md:hidden");
  });

  it("Últimas: em lg na linha 5 nas duas colunas; em xl na coluna da direita, sob a sessão, esticando até o fim do livro", () => {
    const html = render();
    const lado = classesOf(tagWith(html, 'data-testid="pregao-side"'));
    expect(lado).toEqual(expect.arrayContaining(["contents", "xl:flex", "xl:col-start-3", "xl:row-start-1", "xl:row-span-3", "xl:self-stretch"]));
    const ultimas = classesOf(tagWith(html, 'id="pregao-panel-ultimas"'));
    expect(ultimas).toEqual(expect.arrayContaining(["lg:row-start-5", "lg:col-span-2", "xl:flex-1", "xl:[contain:size]"]));
    // sessão e Últimas dentro do bloco da direita
    const start = html.indexOf('data-testid="pregao-side"');
    expect(html.indexOf('aria-labelledby="pregao-h-sessao"')).toBeGreaterThan(start);
    expect(html.indexOf('id="pregao-panel-ultimas"')).toBeGreaterThan(start);
  });

  it("o tablist gruda abaixo do cabeçalho fixo do app (top-14), sob o z-30 dele", () => {
    const tabs = classesOf(tagWith(render(), 'data-testid="pregao-tabs"'));
    expect(tabs).toEqual(expect.arrayContaining(["sticky", "top-14", "z-20"]));
    expect(tabs).not.toContain("top-0");
  });

  it("o contêiner do gráfico tem altura por breakpoint, até xl:h-[420px]", () => {
    const html = render();
    expect(html).toMatch(/h-\[280px\] md:h-\[360px\] xl:h-\[420px\]">\s*<div data-testid="slot-chart"/);
  });
});

describe("PregaoLayout — títulos de seção e landmarks", () => {
  it("cada section[aria-labelledby] aponta para um h3 com esse id", () => {
    const html = render();
    const labelledBy = [...html.matchAll(/<section[^>]*aria-labelledby="([^"]+)"/g)].map((m) => m[1]);
    expect(labelledBy).toHaveLength(8);
    for (const id of labelledBy) {
      expect(html).toMatch(new RegExp(`<h3 id="${id}"[^>]*>`));
    }
  });

  it("títulos de seção estão presentes com os textos exatos", () => {
    const html = render();
    for (const texto of [
      "Fita",
      "Controles",
      "Sessão",
      "Resumo da sessão",
      "Gráfico",
      "Livro de casas",
      "Últimas atualizações",
      "Lista",
    ]) {
      expect(html).toContain(`>${texto}</h3>`);
    }
  });

  it("Fita e Controles são sr-only; os demais títulos são text-sm font-medium", () => {
    const html = render();
    expect(html).toMatch(/<h3 id="pregao-h-fita" class="sr-only">Fita<\/h3>/);
    expect(html).toMatch(/<h3 id="pregao-h-controles" class="sr-only">Controles<\/h3>/);
    for (const id of ["pregao-h-sessao", "pregao-h-resumo", "pregao-h-grafico", "pregao-h-livro", "pregao-h-ultimas", "pregao-h-lista"]) {
      expect(classesOf(tagWith(html, `id="${id}"`))).toEqual(["text-sm", "font-medium"]);
    }
  });
});

describe("PregaoLayout — semântica das abas", () => {
  it("não renderiza role=tabpanel (D38)", () => {
    expect(render()).not.toContain("tabpanel");
  });

  it("o tablist fica oculto em md e acima", () => {
    const html = render();
    expect(classesOf(tagWith(html, 'data-testid="pregao-tabs"'))).toContain("md:hidden");
    expect(tagWith(html, 'data-testid="pregao-tabs"')).toContain('role="tablist"');
  });
});

describe("nextTab", () => {
  it("ArrowRight e ArrowLeft são cíclicos", () => {
    expect(nextTab("grafico", "ArrowRight")).toBe("livro");
    expect(nextTab("ultimas", "ArrowRight")).toBe("grafico");
    expect(nextTab("grafico", "ArrowLeft")).toBe("ultimas");
  });

  it("Home vai ao primeiro e End vai ao último", () => {
    expect(nextTab("lista", "Home")).toBe("grafico");
    expect(nextTab("lista", "End")).toBe("ultimas");
  });

  it("outras teclas devolvem null", () => {
    expect(nextTab("lista", "x")).toBeNull();
    expect(nextTab("lista", "Enter")).toBeNull();
  });
});

describe("PregaoLayout — isolamento de dados", () => {
  it("o módulo não usa hooks de dados nem fetch", () => {
    const fonte = readFileSync(new URL("../pregao-layout.tsx", import.meta.url), "utf8");
    expect(fonte).not.toMatch(/useQuery|use-candles|useSettings|useNow|fetch\(/);
  });
});
