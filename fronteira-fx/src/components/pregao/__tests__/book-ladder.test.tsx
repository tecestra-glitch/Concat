import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { BookLadder, splitBook } from "@/components/pregao/book-ladder";
import { demoBook } from "@/lib/pregao/demo";
import type { BookLevel } from "@/lib/pregao/types";

const NOW = Date.UTC(2026, 10, 2, 12, 0);

function mkLevel(p: Partial<BookLevel> & Pick<BookLevel, "key" | "house" | "source_id">): BookLevel {
  return {
    pair: "USD/PYG",
    city: "CDE",
    channel: "physical",
    kind: "executable",
    buy: "7320",
    sell: "7380",
    spread_pct: null,
    agio_buy_pct: null,
    agio_sell_pct: null,
    status: "open",
    incomplete: false,
    captured_at: new Date(NOW - 60_000).toISOString(),
    data_mode: "real",
    ...p,
  };
}

const houseA = mkLevel({ key: "a", house: "Casa A", source_id: "a", buy: "7300", sell: "7400" });
const houseB = mkLevel({ key: "b", house: "Casa B", source_id: "b", buy: "7320", sell: "7380" });
const houseC = mkLevel({ key: "c", house: "Casa C", source_id: "c", buy: "7310", sell: "7390" });
const bcpRef = mkLevel({
  key: "ref",
  house: "BCP (referência)",
  source_id: "bcp",
  kind: "market_reference",
  city: null,
  channel: "digital",
  buy: "5944.76",
  sell: "5944.76",
});

const baseProps = {
  pair: "USD/PYG" as const,
  quote: "PYG" as const,
  selectedKey: null,
  onSelect: () => {},
  now: NOW,
};

/** Trecho do HTML entre dois testids (lado da compra ou da venda). */
function between(html: string, from: string, to: string): string {
  const start = html.indexOf(`data-testid="${from}"`);
  const end = to ? html.indexOf(`data-testid="${to}"`) : html.length;
  return html.slice(start, end);
}

/** Linhas `<tr>` de um testid, com a abertura e o conteúdo. */
function rowsOf(html: string, testid: string): { open: string; body: string }[] {
  const re = new RegExp(`(<tr\\b[^>]*data-testid="${testid}"[^>]*>)([\\s\\S]*?)<\\/tr>`, "g");
  return [...html.matchAll(re)].map((m) => ({ open: m[1], body: m[2] }));
}

describe("splitBook", () => {
  it("ordena compra por melhor compra (desc) e venda por melhor venda (asc); referência fica só em refs", () => {
    const levels = [houseA, houseB, houseC, bcpRef];
    const { bids, asks, refs } = splitBook(levels);
    expect(bids.map((l) => l.buy)).toEqual(["7320", "7310", "7300"]);
    expect(asks.map((l) => l.sell)).toEqual(["7380", "7390", "7400"]);
    expect(refs.map((l) => l.key)).toEqual(["ref"]);
    expect(bids.some((l) => l.kind === "market_reference")).toBe(false);
    expect(asks.some((l) => l.kind === "market_reference")).toBe(false);
  });

  it("casa com venda nula sai de asks e continua em bids", () => {
    const noSell = mkLevel({ key: "d", house: "Casa D", source_id: "d", buy: "7315", sell: null });
    const { bids, asks } = splitBook([houseA, houseB, houseC, noSell]);
    expect(asks.map((l) => l.key)).not.toContain("d");
    expect(bids.map((l) => l.key)).toContain("d");
    expect(asks.map((l) => l.sell)).toEqual(["7380", "7390", "7400"]);
  });

  it("casa com compra nula sai de bids e continua em asks", () => {
    const noBuy = mkLevel({ key: "e", house: "Casa E", source_id: "e", buy: null, sell: "7350" });
    const { bids, asks } = splitBook([houseA, noBuy]);
    expect(bids.map((l) => l.key)).not.toContain("e");
    expect(asks.map((l) => l.key)).toContain("e");
  });

  it("empate de preço ordena por nome da casa (asc) nos dois lados", () => {
    const zeta = mkLevel({ key: "z", house: "Zeta", source_id: "z", buy: "7320", sell: "7380" });
    const alpha = mkLevel({ key: "x", house: "Alpha", source_id: "x", buy: "7320", sell: "7380" });
    const { bids, asks } = splitBook([zeta, alpha]);
    expect(bids.map((l) => l.house)).toEqual(["Alpha", "Zeta"]);
    expect(asks.map((l) => l.house)).toEqual(["Alpha", "Zeta"]);
  });
});

describe("BookLadder", () => {
  const levels = [houseA, houseB, houseC, bcpRef];

  it("marca data-best e a palavra melhor só na primeira linha de cada lado", () => {
    const html = renderToStaticMarkup(<BookLadder {...baseProps} levels={levels} />);
    const buyRows = rowsOf(between(html, "pregao-book-side-buy", "pregao-book-side-sell"), "pregao-book-row");
    expect(buyRows).toHaveLength(3);
    expect(buyRows[0].open).toContain('data-best="true"');
    expect(buyRows[0].body).toContain("melhor");
    expect(buyRows[1].open).toContain('data-best="false"');
    expect(buyRows[1].body).not.toContain("melhor");
  });

  it("lados não contêm referência; bloco de referência tem linha sem tabindex e com ≈", () => {
    const html = renderToStaticMarkup(<BookLadder {...baseProps} levels={levels} />);
    const buySide = between(html, "pregao-book-side-buy", "pregao-book-side-sell");
    const sellSide = between(html, "pregao-book-side-sell", "pregao-book-reference");
    expect(buySide).not.toContain('data-kind="market_reference"');
    expect(sellSide).not.toContain('data-kind="market_reference"');
    const refBlock = between(html, "pregao-book-reference", "");
    const refRows = rowsOf(refBlock, "pregao-book-ref-row");
    expect(refRows).toHaveLength(1);
    expect(refRows[0].open).toContain('data-kind="market_reference"');
    expect(refRows[0].open).not.toContain("tabindex");
    expect(refRows[0].body).toContain("≈ ");
    expect(refRows[0].body).not.toContain("melhor");
  });

  it("mostra os textos de Compra, Venda e referência exatamente como na spec", () => {
    const html = renderToStaticMarkup(<BookLadder {...baseProps} levels={levels} />);
    expect(html).toContain("quanto a casa paga");
    expect(html).toContain("quanto a casa cobra");
    expect(html).toContain("Preço de referência, não executável. Não é uma casa.");
    expect(html).toContain("Lado da compra");
    expect(html).toContain("Lado da venda");
  });

  it("casa fechada leva o rótulo fechada, sem opacidade (contraste AA); incompleta leva aviso", () => {
    const closed = mkLevel({ key: "f", house: "Casa Fechada", source_id: "f", buy: "7310", sell: "7390", status: "closed" });
    const incomplete = mkLevel({ key: "i", house: "Casa Parcial", source_id: "i", buy: "7305", sell: null, incomplete: true });
    const html = renderToStaticMarkup(<BookLadder {...baseProps} levels={[closed, incomplete]} />);
    const closedRow = rowsOf(html, "pregao-book-row").find((r) => r.open.includes('data-key="f"'));
    expect(closedRow).toBeDefined();
    expect(closedRow?.open).not.toContain("opacity-");
    expect(closedRow?.open).toContain('data-status="closed"');
    expect(closedRow?.body).toContain("fechada");
    const incompleteRow = rowsOf(html, "pregao-book-row").find((r) => r.open.includes('data-key="i"'));
    expect(incompleteRow?.body).toContain("incompleta");
  });

  it("selectedKey marca aria-selected só na linha da chave selecionada", () => {
    const html = renderToStaticMarkup(<BookLadder {...baseProps} levels={levels} selectedKey="b" />);
    const rows = rowsOf(html, "pregao-book-row");
    const selected = rows.filter((r) => r.open.includes('aria-selected="true"'));
    expect(selected.length).toBeGreaterThan(0);
    for (const r of selected) expect(r.open).toContain('data-key="b"');
    for (const r of rows.filter((r) => !r.open.includes('data-key="b"'))) {
      expect(r.open).toContain('aria-selected="false"');
    }
  });

  it("coluna Idade: 'há ' com now > 0 e '—' com now = 0", () => {
    const withNow = renderToStaticMarkup(<BookLadder {...baseProps} levels={levels} now={NOW} />);
    expect(withNow).toContain("há ");
    const noNow = renderToStaticMarkup(<BookLadder {...baseProps} levels={levels} now={0} />);
    expect(noNow).not.toContain("há ");
    expect(noNow).toContain(">—</td>");
  });

  it("Idade curta na célula ('1 min', sem quebra) e a forma longa no title e para leitor de tela", () => {
    const html = renderToStaticMarkup(<BookLadder {...baseProps} levels={[houseA]} now={NOW} />);
    const row = rowsOf(html, "pregao-book-row")[0];
    expect(row.body).toMatch(/<td class="[^"]*whitespace-nowrap[^"]*" title="há 1 min"><span aria-hidden="true">1 min<\/span><span class="sr-only">há 1 min<\/span><\/td>/);
  });

  it("filiais da mesma casa em cidades diferentes levam a sigla da cidade; digital fica sem cidade", () => {
    const chacoCde = mkLevel({ key: "chaco:CDE", house: "Cambios Chaco", source_id: "chaco", city: "CDE", buy: "7320", sell: "7380" });
    const chacoAsu = mkLevel({ key: "chaco:ASU", house: "Cambios Chaco", source_id: "chaco", city: "ASU", buy: "7310", sell: "7390" });
    const alberdiPjc = mkLevel({ key: "alberdi:PJC", house: "Cambios Alberdi", source_id: "alberdi", city: "PJC", buy: "7300", sell: "7400" });
    const ueno = mkLevel({ key: "ueno", house: "ueno", source_id: "ueno", city: null, channel: "digital", buy: "7290", sell: "7410" });
    const html = renderToStaticMarkup(<BookLadder {...baseProps} levels={[chacoCde, chacoAsu, alberdiPjc, ueno]} />);
    const rows = rowsOf(between(html, "pregao-book-side-buy", "pregao-book-side-sell"), "pregao-book-row");
    const cityOf = (key: string) => {
      const row = rows.find((r) => r.open.includes(`data-key="${key}"`));
      expect(row, key).toBeDefined();
      return row!.body.match(/data-testid="pregao-book-city"[^>]*title="([^"]+)">([A-Z]{3})/)?.slice(1);
    };
    expect(cityOf("chaco:CDE")).toEqual(["Ciudad del Este", "CDE"]);
    expect(cityOf("chaco:ASU")).toEqual(["Asunción", "ASU"]);
    expect(cityOf("alberdi:PJC")).toEqual(["Pedro Juan Caballero", "PJC"]);
    expect(rows.find((r) => r.open.includes('data-key="ueno"'))?.body).not.toContain("pregao-book-city");
    // A mesma casa em duas cidades vira duas linhas distinguíveis pelo texto visível.
    const visible = rows.map((r) => r.body.replace(/<span class="sr-only">[^<]*<\/span>/g, "").replace(/<[^>]+>/g, ""));
    expect(visible.filter((t) => t.startsWith("Cambios ChacoCDE"))).toHaveLength(1);
    expect(visible.filter((t) => t.startsWith("Cambios ChacoASU"))).toHaveLength(1);
  });

  it("sem casas (vazio ou só referências) → data-state empty e mensagem exata", () => {
    const empty = renderToStaticMarkup(<BookLadder {...baseProps} levels={[]} />);
    expect(empty).toContain('data-state="empty"');
    expect(empty).toContain("Nenhuma casa publicou cotação para este par.");
    const onlyRef = renderToStaticMarkup(<BookLadder {...baseProps} levels={[bcpRef]} />);
    expect(onlyRef).toContain('data-state="empty"');
    expect(onlyRef).toContain("Nenhuma casa publicou cotação para este par.");
  });

  it("sem referência para o par → seção informa 'Sem referência para este par.'", () => {
    const html = renderToStaticMarkup(<BookLadder {...baseProps} levels={[houseA, houseB]} />);
    expect(html).toContain('data-testid="pregao-book-reference"');
    expect(html).toContain("Sem referência para este par.");
    expect(html).toContain('data-state="ready"');
  });

  it("estado carregando: data-state loading, aria-busy e texto Carregando…", () => {
    const html = renderToStaticMarkup(<BookLadder {...baseProps} levels={levels} loading />);
    expect(html).toContain('data-state="loading"');
    expect(html).toContain('aria-busy="true"');
    expect(html).toContain("Carregando…");
  });

  it("erro: role alert, mensagem, e botão Tentar de novo só quando há onRetry; loading vence erro", () => {
    const withRetry = renderToStaticMarkup(
      <BookLadder {...baseProps} levels={levels} error={new Error("HTTP 500")} onRetry={() => {}} />,
    );
    expect(withRetry).toContain('data-state="error"');
    expect(withRetry).toContain('role="alert"');
    expect(withRetry).toContain("Não foi possível carregar o livro.");
    expect(withRetry).toContain("HTTP 500");
    expect(withRetry).toContain("Tentar de novo");
    const noRetry = renderToStaticMarkup(<BookLadder {...baseProps} levels={levels} error={new Error("x")} />);
    expect(noRetry).not.toContain("Tentar de novo");
    const both = renderToStaticMarkup(<BookLadder {...baseProps} levels={levels} loading error={new Error("x")} />);
    expect(both).toContain('data-state="loading"');
  });

  it("data-mode=demo quando os níveis são demo", () => {
    const demo = levels.map((l) => ({ ...l, data_mode: "demo" as const }));
    const html = renderToStaticMarkup(<BookLadder {...baseProps} levels={demo} />);
    expect(html).toContain('data-mode="demo"');
  });

  it("com demoBook: alberdi é a melhor compra, ueno a melhor venda, bcp é a referência", () => {
    const now = new Date(NOW);
    const levelsDemo = demoBook("USD/PYG", now);
    const { bids, asks, refs } = splitBook(levelsDemo);
    expect(bids[0].source_id).toBe("alberdi");
    expect(asks[0].source_id).toBe("ueno");
    expect(refs[0].source_id).toBe("bcp");
    const html = renderToStaticMarkup(<BookLadder {...baseProps} levels={levelsDemo} />);
    expect(html).toContain('data-mode="demo"');
  });
});
