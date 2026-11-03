import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { demoWatchlist } from "@/lib/pregao/demo";
import type { WatchlistRow } from "@/lib/pregao/types";
import { Sparkline, sparklinePoints, trendLabel } from "../sparkline";
import { WATCHLIST_COLUMNS, Watchlist, type WatchlistProps } from "../watchlist";

const NOW = new Date(Date.UTC(2026, 10, 2, 12));
const ROWS = demoWatchlist("USD/PYG", NOW);

function renderList(props: Partial<WatchlistProps> = {}, rows: WatchlistRow[] = ROWS): string {
  return renderToStaticMarkup(<Watchlist rows={rows} selectedKey={null} onSelect={() => {}} {...props} />);
}

/** Markup de uma linha (`<tr>`) pela sua `data-key`. */
function rowHtml(html: string, key: string): string {
  const start = html.indexOf(`data-key="${key}"`);
  if (start < 0) return "";
  const open = html.lastIndexOf("<tr", start);
  const end = html.indexOf("</tr>", start);
  return html.slice(open, end + "</tr>".length);
}

/** Markup das células `<td data-col="…">` de uma coluna, em todas as linhas. */
function cellsHtml(html: string, col: string): string[] {
  return html.match(new RegExp(`<td[^>]*data-col="${col}"[^>]*>.*?</td>`, "g")) ?? [];
}

/** Ordem crescente de spread com nulos por último (regra de §14.3, item 4). */
function bySpreadNullsLast(a: WatchlistRow, b: WatchlistRow): number {
  if (a.spread_pct === null) return b.spread_pct === null ? 0 : 1;
  if (b.spread_pct === null) return -1;
  return a.spread_pct - b.spread_pct;
}

function firstHouseRow(rows: WatchlistRow[]): WatchlistRow {
  const row = rows.find((r) => r.kind !== "market_reference");
  if (!row) throw new Error("demo sem casa");
  return row;
}

describe("sparklinePoints", () => {
  it("começa e termina nos cantos com padding de 1 px", () => {
    const points = sparklinePoints([1, 2], 10, 10);
    expect(points.startsWith("1.00,9.00 ")).toBe(true);
    expect(points.endsWith("9.00,1.00")).toBe(true);
  });

  it("usa metade da altura para todos os pontos quando max e min são iguais", () => {
    const ys = sparklinePoints([5, 5, 5], 10, 10)
      .split(" ")
      .map((p) => p.split(",")[1]);
    expect(ys).toEqual(["5.00", "5.00", "5.00"]);
  });

  it("devolve string vazia com menos de dois valores", () => {
    expect(sparklinePoints([1], 10, 10)).toBe("");
  });

  it("nunca produz NaN", () => {
    const cases: number[][] = [[], [1], [1, 2], [5, 5, 5], [1, 0, -3, 7]];
    for (const values of cases) expect(sparklinePoints(values, 72, 20)).not.toContain("NaN");
  });
});

describe("trendLabel", () => {
  it("descreve alta com duas casas decimais", () => {
    expect(trendLabel([100, 100.84])).toBe("Tendência: subiu 0,84 %");
  });

  it("descreve queda", () => {
    expect(trendLabel([2, 1]).startsWith("Tendência: caiu")).toBe(true);
  });

  it("descreve variação nula como estável", () => {
    expect(trendLabel([3, 3])).toBe("Tendência: estável");
  });

  it("sem pontos suficientes diz que não há dados", () => {
    expect(trendLabel([1])).toBe("Tendência: sem dados");
  });
});

describe("Sparkline", () => {
  it("desenha svg com role img, rótulo, polyline e ponto final sem cor de alta ou baixa", () => {
    const html = renderToStaticMarkup(<Sparkline values={[1, 2, 3]} />);
    expect(html).toContain('role="img"');
    expect(html).toContain('aria-label="Tendência: subiu 200,00 %"');
    expect(html).toContain("<polyline");
    expect(html).toContain("<circle");
    expect(html).not.toContain("text-gain");
    expect(html).not.toContain("text-loss");
  });

  it("com menos de dois valores mostra travessão sem svg", () => {
    const html = renderToStaticMarkup(<Sparkline values={[1]} />);
    expect(html).toContain("—");
    expect(html).not.toContain("<svg");
  });
});

describe("WATCHLIST_COLUMNS", () => {
  it("lista os ids na ordem da spec", () => {
    expect([...WATCHLIST_COLUMNS]).toEqual(["pair", "house", "city", "buy", "sell", "spread", "delta", "trend", "status"]);
  });
});

describe("Watchlist", () => {
  it("marca Spread como ordenação ascendente e as demais colunas ordenáveis como none", () => {
    const html = renderList();
    const ths = html.match(/<th[^>]*>.*?<\/th>/g) ?? [];
    const spreadTh = ths.find((th) => th.includes(">Spread"));
    expect(spreadTh).toContain('aria-sort="ascending"');
    const sorts = ths.map((th) => th.match(/aria-sort="(\w+)"/)?.[1]).filter((s): s is string => s !== undefined);
    expect(sorts.filter((s) => s === "ascending")).toHaveLength(1);
    expect(sorts.filter((s) => s === "none")).toHaveLength(7);
  });

  it("ordena as linhas por spread crescente com nulos por último", () => {
    const html = renderList();
    const keys = [...html.matchAll(/data-key="([^"]+)"/g)].map((m) => m[1]);
    expect(keys).toEqual([...ROWS].sort(bySpreadNullsLast).map((r) => r.key));
  });

  it("linha de referência fica desabilitada, fora da ordem de foco, com selo e prefixo ≈", () => {
    const html = renderList();
    const ref = html.match(/<tr[^>]*data-kind="market_reference"[^>]*>/)?.[0] ?? "";
    expect(ref).toContain('aria-disabled="true"');
    expect(ref).toContain('tabindex="-1"');
    const refRow = html.match(/<tr[^>]*data-kind="market_reference"[^>]*>.*?<\/tr>/)?.[0] ?? "";
    expect(refRow).toContain("≈ ");
    expect(refRow).toContain("pregao-reference-badge");
  });

  it("linhas de casas são focáveis com tabindex 0", () => {
    const html = renderList();
    const houseRows = ROWS.filter((r) => r.kind !== "market_reference");
    expect(houseRows.length).toBeGreaterThan(0);
    for (const row of houseRows) expect(rowHtml(html, row.key)).toContain('tabindex="0"');
  });

  it("marca somente a linha de selectedKey como selecionada", () => {
    const target = firstHouseRow(ROWS);
    const html = renderList({ selectedKey: target.key });
    expect(html.match(/aria-selected="true"/g)).toHaveLength(1);
    expect(html.match(/data-state="selected"/g)).toHaveLength(1);
    expect(rowHtml(html, target.key)).toContain('aria-selected="true"');
    expect(rowHtml(html, target.key)).toContain('data-state="selected"');
  });

  it("referência nunca fica selecionada, mesmo quando a chave está em selectedKey", () => {
    const ref = ROWS.find((r) => r.kind === "market_reference");
    if (!ref) throw new Error("demo sem referência");
    const html = renderList({ selectedKey: ref.key });
    expect(rowHtml(html, ref.key)).not.toContain('aria-selected="true"');
  });

  it("linha fechada diz fechada, sem opacidade (contraste AA)", () => {
    const target = firstHouseRow(ROWS);
    const rows = ROWS.map((r) => (r.key === target.key ? { ...r, status: "closed" as const } : r));
    const row = rowHtml(renderList({}, rows), target.key);
    expect(row).not.toContain("opacity-");
    expect(row).toContain('data-status="closed"');
    expect(row).toContain("fechada");
  });

  it("linha incompleta mostra o aviso incompleta", () => {
    const target = firstHouseRow(ROWS);
    const rows = ROWS.map((r) => (r.key === target.key ? { ...r, incomplete: true, sell: null } : r));
    expect(rowHtml(renderList({}, rows), target.key)).toContain("incompleta");
  });

  it("células de Compra e Venda não usam cor de alta ou baixa", () => {
    const html = renderList();
    const buy = cellsHtml(html, "buy");
    const sell = cellsHtml(html, "sell");
    expect(buy.length).toBe(ROWS.length);
    expect(sell.length).toBe(ROWS.length);
    for (const cell of [...buy, ...sell]) {
      expect(cell).not.toContain("text-gain");
      expect(cell).not.toContain("text-loss");
    }
  });

  it("sem linhas mostra a mensagem de vazio", () => {
    expect(renderList({}, [])).toContain("Nenhuma série na lista.");
  });

  it("erro mostra alerta com a mensagem de falha", () => {
    const html = renderList({ error: new Error("timeout") }, []);
    expect(html).toContain('role="alert"');
    expect(html).toContain("Não foi possível carregar a lista.");
    expect(html).toContain('data-state="error"');
  });

  it("carregando mostra estado de carregamento com aria-busy", () => {
    const html = renderList({ loading: true }, []);
    expect(html).toContain('data-state="loading"');
    expect(html).toContain('aria-busy="true"');
    expect(html).toContain("Carregando…");
  });

  it("pronto marca data-state ready e a legenda da tabela", () => {
    const html = renderList();
    expect(html).toContain('data-testid="pregao-watchlist"');
    expect(html).toContain('data-state="ready"');
    expect(html).toContain("Lista de séries acompanhadas");
  });
});

describe("Watchlist: larguras estreitas", () => {
  /** Classes da célula `<td data-col="…">` da primeira linha e do `<th>` correspondente. */
  function colClasses(html: string, col: string): string {
    return cellsHtml(html, col)[0]?.match(/class="([^"]*)"/)?.[1] ?? "";
  }

  it("no celular ficam casa, compra, venda e variação; par, cidade, spread, tendência e estado saem", () => {
    const html = renderList();
    for (const col of ["pair", "city", "spread", "trend", "status"]) expect(colClasses(html, col), col).toContain("max-sm:hidden");
    for (const col of ["house", "buy", "sell", "delta"]) expect(colClasses(html, col), col).not.toContain("max-sm:hidden");
    const ths = html.match(/<th[^>]*>/g) ?? [];
    expect(ths.filter((th) => th.includes("max-sm:hidden"))).toHaveLength(5);
  });

  it("casa e cidade não quebram linha: nowrap, nome truncado com title", () => {
    const html = renderList();
    expect(colClasses(html, "house")).toContain("whitespace-nowrap");
    expect(colClasses(html, "city")).toContain("whitespace-nowrap");
    const casa = firstHouseRow(ROWS);
    const row = rowHtml(html, casa.key);
    expect(row).toMatch(/<span class="max-w-\[10rem\] truncate" title="[^"]+">/);
    expect(row).toContain("inline-flex flex-nowrap");
  });

  it("filial distinguível no celular: sigla da cidade (nome no title e sr-only) e estado sob o nome", () => {
    const html = renderList();
    const casa = ROWS.find((r) => r.kind !== "market_reference" && r.city !== null);
    if (!casa?.city) throw new Error("demo sem casa presencial");
    const sub = rowHtml(html, casa.key).match(/data-testid="pregao-watchlist-house-sub"[^>]*>(.*?)<\/span><\/span><\/td>/)?.[0] ?? "";
    expect(sub).toContain("sm:hidden");
    expect(sub).toMatch(new RegExp(`data-testid="pregao-watchlist-city"[^>]*title="[^"]+"><span aria-hidden="true">${casa.city}</span><span class="sr-only">[^,<]+</span>`));
    expect(sub).toContain('data-testid="pregao-watchlist-status"');
  });

  it("coluna Cidade: nome inteiro só em xl; abaixo, a sigla", () => {
    const html = renderList();
    const casa = ROWS.find((r) => r.kind !== "market_reference" && r.city !== null)!;
    const cell = rowHtml(html, casa.key).match(/<td[^>]*data-col="city"[^>]*>.*?<\/td>/)?.[0] ?? "";
    expect(cell).toMatch(/class="block max-w-\[10rem\] truncate max-xl:hidden"/);
    expect(cell).toMatch(/data-testid="pregao-watchlist-city" class="[^"]*xl:hidden/);
  });
});
