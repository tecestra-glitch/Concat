import { createElement, isValidElement, type ReactElement, type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { DEMO_HOUSES } from "@/lib/pregao/demo";
import { demoHeat } from "@/lib/pregao/demo";
import { PAIR_LABEL, PAIRS, type HeatCell } from "@/lib/pregao/types";
import {
  HEAT_LEGEND,
  SpreadHeatmap,
  heatCellLabel,
  heatStep,
  type SpreadHeatmapProps,
} from "@/components/pregao/spread-heatmap";

const NOW = new Date(Date.UTC(2026, 10, 2, 12));
const HOUSES = DEMO_HOUSES.filter((h) => !h.reference).map((h) => ({ source_id: h.id, house: h.name }));
const DEMO_CELLS = demoHeat(NOW);

const CELL: HeatCell = {
  key: "chaco:CDE:USD/PYG:cash",
  pair: "USD/PYG",
  source_id: "chaco",
  house: "Cambios Chaco",
  spread_pct: 1.1784,
  status: "open",
  captured_at: "2026-11-02T11:59:00Z",
};
const SYNTH_HOUSES = [
  { source_id: "chaco", house: "Cambios Chaco" },
  { source_id: "nomad", house: "Nomad" },
];

function render(overrides: Partial<SpreadHeatmapProps> = {}): string {
  const props: SpreadHeatmapProps = {
    cells: DEMO_CELLS,
    houses: HOUSES,
    selectedKey: null,
    onSelect: () => {},
    ...overrides,
  };
  return renderToStaticMarkup(createElement(SpreadHeatmap, props));
}

function count(html: string, needle: string): number {
  return html.split(needle).length - 1;
}

function decode(s: string): string {
  return s
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#x27;/g, "'")
    .replace(/&amp;/g, "&");
}

/** Trecho `<td …>…` (até o próximo `<td`) da célula com a chave dada. */
function cellByKey(html: string, key: string): string {
  const chunk = html.split("<td").find((c) => c.includes(`data-key="${key}"`));
  if (!chunk) throw new Error(`célula ${key} não encontrada`);
  return chunk;
}

/** Trecho da linha (`<tr>`) cujo cabeçalho de linha é a casa dada. */
function rowOf(html: string, house: string): string {
  const row = html.split("<tr>").find((r) => r.includes(`>${house}</th>`));
  if (!row) throw new Error(`linha ${house} não encontrada`);
  return row;
}

function cellsIn(row: string): string[] {
  return row.split("<td").slice(1);
}

type AnyElement = ReactElement<Record<string, unknown>>;

/** Procura o primeiro elemento da árvore devolvida por `SpreadHeatmap(props)` que satisfaz o predicado. */
function findFirst(node: ReactNode, pred: (el: AnyElement) => boolean): AnyElement | null {
  if (Array.isArray(node)) {
    for (const child of node) {
      const found = findFirst(child, pred);
      if (found) return found;
    }
    return null;
  }
  if (!isValidElement<Record<string, unknown>>(node)) return null;
  if (pred(node)) return node;
  return findFirst(node.props.children as ReactNode, pred);
}

describe("heatStep", () => {
  it("mapeia spread (já ×100) para os degraus 1 a 5 e trata nulo e NaN como 0", () => {
    expect(heatStep(0.4)).toBe(1);
    expect(heatStep(0.5)).toBe(2);
    expect(heatStep(1)).toBe(3);
    expect(heatStep(2)).toBe(4);
    expect(heatStep(4)).toBe(5);
    expect(heatStep(9)).toBe(5);
    expect(heatStep(null)).toBe(0);
    expect(heatStep(Number.NaN)).toBe(0);
  });
});

describe("HEAT_LEGEND e heatCellLabel", () => {
  it("legenda tem cinco degraus com os rótulos exatos", () => {
    expect(HEAT_LEGEND.map((l) => l.step)).toEqual([1, 2, 3, 4, 5]);
    expect(HEAT_LEGEND.map((l) => l.label)).toEqual(["< 0,5 %", "0,5–1 %", "1–2 %", "2–4 %", "≥ 4 %"]);
  });

  it("rotula a célula com casa, par e spread", () => {
    expect(heatCellLabel(CELL)).toBe("Cambios Chaco, USD/PYG: spread 1,18 %");
  });

  it("acrescenta ', fechada' quando a casa está fechada", () => {
    expect(heatCellLabel({ ...CELL, status: "closed" })).toBe("Cambios Chaco, USD/PYG: spread 1,18 %, fechada");
  });

  it("sem spread numérico o rótulo é 'sem spread'", () => {
    expect(heatCellLabel({ ...CELL, spread_pct: null })).toBe("sem spread");
  });
});

describe("SpreadHeatmap — estrutura", () => {
  it("monta uma linha por casa e uma coluna por par, com caption e cabeçalhos", () => {
    const html = render();
    expect(html).toContain('<caption class="sr-only">Spread por casa e par</caption>');
    expect(count(html, 'scope="row"')).toBe(HOUSES.length);
    for (const p of PAIRS) expect(html).toContain(`>${PAIR_LABEL[p]}</th>`);
    // Cabeçalho vazio "Casa" + um cabeçalho por par.
    expect(count(html, 'scope="col"')).toBe(PAIRS.length + 1);
    expect(html).toContain('<span class="sr-only">Casa</span>');
  });

  it("uma célula clicável por casa e par no demo", () => {
    const html = render();
    expect(count(html, 'data-testid="pregao-heat-cell"')).toBe(HOUSES.length * PAIRS.length);
  });

  it("prop pairs restringe as colunas", () => {
    const html = render({ pairs: ["USD/PYG"] });
    expect(count(html, 'scope="col"')).toBe(2);
    expect(html).not.toContain(`>${PAIR_LABEL["BRL/PYG"]}</th>`);
  });

  it("legenda é uma lista ordenada com cinco degraus", () => {
    const html = decode(render({ cells: [CELL], houses: SYNTH_HOUSES }));
    const legend = html.slice(html.indexOf('<ol aria-label="Legenda do spread"'));
    expect(legend.split("<li").length - 1).toBe(5);
    for (const { label } of HEAT_LEGEND) expect(legend).toContain(label);
  });
});

describe("SpreadHeatmap — células", () => {
  it("célula com spread: data-step, texto, aria-label e fundo de degrau; casa sem célula fica desabilitada", () => {
    const html = render({ cells: [CELL], houses: SYNTH_HOUSES });
    const chaco = cellByKey(html, CELL.key);
    expect(chaco).toContain('data-step="3"');
    expect(chaco).toContain('class="bg-[var(--heat-3)]"');
    expect(chaco).toContain('aria-label="Cambios Chaco, USD/PYG: spread 1,18 %"');
    expect(chaco).toMatch(/>1,18 %<\/button>/);

    const nomadUsd = cellsIn(rowOf(html, "Nomad"))[0];
    expect(nomadUsd).toContain('data-step="0"');
    expect(nomadUsd).toContain('aria-label="sem spread"');
    expect(nomadUsd).toContain("disabled");
    expect(nomadUsd).toMatch(/>—<\/button>/);
  });

  it("com duas células para a mesma casa e par, vale a de captured_at mais recente", () => {
    const newer: HeatCell = { ...CELL, spread_pct: 2.5, captured_at: "2026-11-02T12:00:00Z" };
    const html = render({ cells: [CELL, newer], houses: SYNTH_HOUSES });
    const chaco = cellByKey(html, CELL.key);
    expect(chaco).toContain('data-step="4"');
    expect(chaco).toMatch(/>2,50 %<\/button>/);

    const reversed = render({ cells: [newer, CELL], houses: SYNTH_HOUSES });
    expect(cellByKey(reversed, CELL.key)).toContain('data-step="4"');
  });

  it("status fechada: aria-label termina em ', fechada' e a célula ganha contorno tracejado (sem opacidade, contraste AA)", () => {
    const html = render({ cells: [{ ...CELL, status: "closed" }], houses: SYNTH_HOUSES });
    const chaco = cellByKey(html, CELL.key);
    expect(chaco).toContain('aria-label="Cambios Chaco, USD/PYG: spread 1,18 %, fechada"');
    expect(chaco).not.toContain("opacity-");
    expect(chaco).toContain("border-dashed");
  });

  it("aria-pressed fica true só na célula selecionada", () => {
    const html = render({ cells: [CELL], houses: SYNTH_HOUSES, selectedKey: CELL.key });
    expect(cellByKey(html, CELL.key)).toContain('aria-pressed="true"');
    expect(count(html, 'aria-pressed="true"')).toBe(1);

    const none = render({ cells: [CELL], houses: SYNTH_HOUSES, selectedKey: null });
    expect(count(none, 'aria-pressed="true"')).toBe(0);
  });

  it("clicar numa célula chama onSelect com a chave da célula", () => {
    const picked: string[] = [];
    const tree = SpreadHeatmap({
      cells: [CELL],
      houses: SYNTH_HOUSES,
      selectedKey: null,
      onSelect: (key) => picked.push(key),
    });
    const button = findFirst(tree, (el) => el.props["data-key"] === CELL.key);
    expect(button).not.toBeNull();
    (button?.props.onClick as () => void)();
    expect(picked).toEqual([CELL.key]);
  });
});

describe("SpreadHeatmap — estados", () => {
  it("sem casas ou sem spread numérico mostra estado vazio", () => {
    const empty = decode(render({ cells: [], houses: HOUSES }));
    expect(empty).toContain('data-state="empty"');
    expect(empty).toContain("Sem spreads para montar o mapa.");
    expect(empty).not.toContain("<table");

    const noHouses = render({ cells: DEMO_CELLS, houses: [] });
    expect(noHouses).toContain('data-state="empty"');

    const allNull = render({ cells: [{ ...CELL, spread_pct: null }], houses: SYNTH_HOUSES });
    expect(allNull).toContain('data-state="empty"');
  });

  it("carregando: data-state loading, aria-busy e texto sr-only, sem tabela", () => {
    const html = render({ loading: true });
    expect(html).toContain('data-testid="pregao-heatmap"');
    expect(html).toContain('data-state="loading"');
    expect(html).toContain('aria-busy="true"');
    expect(html).toContain('<span class="sr-only">Carregando…</span>');
    expect(html).not.toContain("<table");
  });

  it("pronto: data-state ready e sem aria-busy", () => {
    const html = render({ cells: [CELL], houses: SYNTH_HOUSES });
    expect(html).toContain('data-state="ready"');
    expect(html).not.toContain("aria-busy");
    expect(html).toContain("<table");
  });
});

describe("SpreadHeatmap — acessibilidade e tokens", () => {
  it("sem cor de alta ou baixa no texto e sem #hex no fonte", () => {
    const html = render();
    for (const cls of ["text-gain", "text-loss", "text-accent"]) expect(html).not.toContain(cls);
    const source = readFileSync(new URL("../spread-heatmap.tsx", import.meta.url), "utf8");
    expect(source).not.toMatch(/#[0-9a-fA-F]{3,8}\b/);
  });
});
