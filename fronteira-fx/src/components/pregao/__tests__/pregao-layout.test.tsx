import { readFileSync } from "node:fs";
import type { ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { MOBILE_TABS, PregaoLayout, nextTab, type PregaoLayoutProps } from "../pregao-layout";

const SLOT_NAMES = ["banner", "ticker", "controls", "timeframe", "indicators", "stats", "chart", "book", "bookExtra", "prints", "watchlist", "clocks"] as const;

function slotNodes(): Record<(typeof SLOT_NAMES)[number], ReactNode> {
  return {
    banner: <div data-testid="slot-banner" />,
    ticker: <div data-testid="slot-ticker" />,
    controls: <div data-testid="slot-controls" />,
    timeframe: <div data-testid="slot-timeframe" />,
    indicators: <div data-testid="slot-indicators" />,
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
  it("renderiza os 12 slots", () => {
    const html = render();
    for (const name of SLOT_NAMES) {
      expect(html).toContain(`data-testid="slot-${name}"`);
    }
    expect(html.match(/data-testid="slot-/g)?.length).toBe(12);
  });

  it("envolve o banner em pregao-banner", () => {
    const html = render();
    expect(html).toMatch(/data-testid="pregao-banner"[^>]*>\s*<div data-testid="slot-banner"/);
  });

  it("a nota do pregão some abaixo de md (a faixa global de demonstração já avisa)", () => {
    expect(classesOf(tagWith(render(), 'data-testid="pregao-banner"'))).toContain("max-md:hidden");
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
    // As abas são `FxSegmented` (fx-segmented): id `pregao-tab-*`; os painéis se rotulam por `aria-labelledby`.
    for (const id of ["grafico", "lista", "ultimas", "livro"] as const) {
      const tag = tabTag(html, id);
      expect(tag).toContain(`id="pregao-tab-${id}"`);
      expect(tag).toContain('role="tab"');
    }
    expect(html).toContain('aria-labelledby="pregao-tab-livro"');
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

describe("PregaoLayout — controles do gráfico", () => {
  it("intervalo e indicadores só aparecem no celular com a aba Gráfico; o par vale para todas as abas", () => {
    const grafico = render();
    for (const id of ["pregao-controls-tf", "pregao-controls-ind"]) {
      expect(classesOf(tagWith(grafico, `data-testid="${id}"`))).toEqual(["contents"]);
    }
    for (const tab of ["livro", "lista", "ultimas"] as const) {
      const html = render({ defaultTab: tab });
      for (const id of ["pregao-controls-tf", "pregao-controls-ind"]) {
        expect(classesOf(tagWith(html, `data-testid="${id}"`)), `${tab} ${id}`).toContain("max-md:hidden");
      }
      expect(classesOf(tagWith(html, 'data-testid="pregao-controls-pair"'))).not.toContain("max-md:hidden");
    }
  });

  it("abas antes dos controles (no celular sobem para a primeira metade da tela)", () => {
    const html = render();
    expect(html.indexOf('data-testid="pregao-tabs"')).toBeLessThan(html.indexOf('aria-labelledby="pregao-h-controles"'));
  });

  it("ordem de foco no celular = ordem visual: nenhum controle do gráfico é reordenado por CSS (sem order-*)", () => {
    const html = render();
    for (const id of ["pregao-controls-tf", "pregao-controls-pair", "pregao-controls-ind"]) {
      const classes = classesOf(tagWith(html, `data-testid="${id}"`));
      expect(classes.filter((c) => /(^|:)order-/.test(c)), id).toEqual([]);
    }
  });

  it("ordem no md+: intervalo, par, indicadores numa linha só", () => {
    const html = render();
    const tf = html.indexOf('data-testid="slot-timeframe"');
    const pair = html.indexOf('data-testid="slot-controls"');
    const ind = html.indexOf('data-testid="slot-indicators"');
    expect(tf).toBeGreaterThan(-1);
    expect(pair).toBeGreaterThan(tf);
    expect(ind).toBeGreaterThan(pair);
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
    expect(sessao).toEqual(expect.arrayContaining(["lg:row-start-1", "lg:row-span-2", "lg:col-start-2", "max-lg:order-[-9998]"]));
    // Celular: abas primeiro (sempre na primeira metade da tela), depois a sessão, depois os controles.
    expect(classesOf(tagWith(html, 'data-testid="pregao-tabs"'))).toContain("order-first");
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

  it("o contêiner do gráfico tem altura por breakpoint, por token de painel (spec PR6)", () => {
    const html = render();
    expect(html).toMatch(/h-\(--panel-h-sm\) md:h-\(--panel-h-md\) xl:h-\(--panel-h-lg\)">\s*<div data-testid="slot-chart"/);
  });
});

describe("PregaoLayout — títulos de seção e landmarks", () => {
  it("cada section[aria-labelledby] aponta para um h3 com esse id", () => {
    const html = render();
    // Seções de aba (role=tabpanel) são nomeadas pela aba, não por um h3: ficam de fora desta conta.
    const labelledBy = [...html.matchAll(/<section(?![^>]*role="tabpanel")[^>]*aria-labelledby="([^"]+)"/g)].map((m) => m[1]);
    expect(labelledBy).toHaveLength(5);
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
  it("cada painel das abas é role=tabpanel e aponta para a sua aba (aria-labelledby)", () => {
    const html = render();
    const paineis: [string, string[]][] = [
      ["grafico", ["pregao-panel-grafico"]],
      ["livro", ["pregao-panel-livro", "pregao-panel-livro-extra"]],
      ["lista", ["pregao-panel-lista"]],
      ["ultimas", ["pregao-panel-ultimas"]],
    ];
    for (const [aba, ids] of paineis) {
      for (const id of ids) {
        const tag = tagWith(html, `id="${id}"`);
        expect(tag, id).toContain('role="tabpanel"');
        expect(tag, id).toContain(`aria-labelledby="pregao-tab-${aba}"`);
      }
    }
    expect(html.match(/role="tabpanel"/g)?.length).toBe(5);
  });

  it("o painel de aba tem a própria aba como nome; o título h3 continua visível dentro dele", () => {
    const html = render();
    expect(tagWith(html, 'id="pregao-panel-livro"')).not.toContain('aria-labelledby="pregao-h-livro"');
    expect(html).toContain('<h3 id="pregao-h-livro" class="text-sm font-medium">Livro de casas</h3>');
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
