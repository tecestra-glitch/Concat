import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { TickerTape, tickerLabel } from "@/components/pregao/ticker-tape";
import { formatRate } from "@/lib/format";
import { DEFAULT_SERIES_KEY, demoTicker } from "@/lib/pregao/demo";
import type { TickerItem } from "@/lib/pregao/types";

const NOW = new Date(Date.UTC(2026, 10, 2, 12));

/** Todos os `<li>` da fita, na ordem do HTML. */
const listItems = (html: string): string[] => html.match(/<li\b[^>]*>[\s\S]*?<\/li>/g) ?? [];

/** `<li>` de uma série pela chave. */
function liOf(html: string, key: string): string {
  const found = listItems(html).find((li) => li.includes(`data-key="${key}"`));
  if (!found) throw new Error(`item ${key} não encontrado`);
  return found;
}

function itemOf(items: TickerItem[], sourceId: string): TickerItem {
  const found = items.find((i) => i.source_id === sourceId);
  if (!found) throw new Error(`casa ${sourceId} não encontrada na fita demo`);
  return found;
}

describe("TickerTape: fita estática (spec PR1)", () => {
  it("sem laço: cada série aparece uma vez, sem cópia de leitor de tela", () => {
    const items = demoTicker(NOW);
    const html = renderToStaticMarkup(<TickerTape items={items} />);

    expect(listItems(html)).toHaveLength(items.length);
    expect(html).not.toContain("data-dup");
  });

  it("sem animação de deslocamento e sem botão de pausa", () => {
    const html = renderToStaticMarkup(<TickerTape items={demoTicker(NOW)} />);

    expect(html).not.toContain("pregao-marquee");
    expect(html).not.toContain("--tape-duration");
    expect(html).not.toContain("Pausar fita");
  });

  it("rolagem horizontal manual no contêiner, com foco por teclado", () => {
    const html = renderToStaticMarkup(<TickerTape items={demoTicker(NOW)} />);

    expect(html).toContain('data-testid="pregao-ticker-scroll"');
    expect(html).toContain("overflow-x-auto");
    expect(html).toContain('tabindex="0"');
  });
});

describe("TickerTape: itens", () => {
  it("par com bandeiras, texto contínuo e rótulo da casa", () => {
    const items = demoTicker(NOW);
    const chaco = itemOf(items, "chaco");
    const html = renderToStaticMarkup(<TickerTape items={items} onSelect={() => {}} />);
    const li = liOf(html, chaco.key);

    expect(li).toContain("svg");
    expect(li).toContain(chaco.house);
  });

  it("referência é texto com ≈ e selo, sem botão", () => {
    const items = demoTicker(NOW);
    const bcp = itemOf(items, "bcp");
    const html = renderToStaticMarkup(<TickerTape items={items} onSelect={() => {}} />);
    const li = liOf(html, bcp.key);

    expect(li).toContain("≈ ");
    expect(li).toContain("pregao-reference-badge");
    expect(li).not.toContain("<button");
  });

  it("selectedKey marca o item com aria-current e cor de destaque", () => {
    const items = demoTicker(NOW);
    const html = renderToStaticMarkup(<TickerTape items={items} selectedKey={DEFAULT_SERIES_KEY} onSelect={() => {}} />);
    const selected = liOf(html, DEFAULT_SERIES_KEY);
    const other = items.find((i) => i.key !== DEFAULT_SERIES_KEY);
    if (!other) throw new Error("fita demo com um único item");

    expect(selected).toContain('aria-current="true"');
    expect(selected).toContain("text-accent");
    expect(liOf(html, other.key)).not.toContain("aria-current");
  });

  it("incompleto vira aviso com texto sr-only", () => {
    const items = demoTicker(NOW);
    const chaco = items.find((i) => i.key === DEFAULT_SERIES_KEY);
    if (!chaco) throw new Error("série padrão ausente na fita demo");
    const html = renderToStaticMarkup(<TickerTape items={[{ ...chaco, incomplete: true }]} />);

    expect(liOf(html, chaco.key)).toContain("cotação incompleta");
    expect(liOf(html, chaco.key)).toContain("bg-warn/15");
  });

  it("variação nula vira data-direction none; alta vira up com texto de leitor de tela", () => {
    const items = demoTicker(NOW);
    const chaco = items.find((i) => i.key === DEFAULT_SERIES_KEY);
    if (!chaco) throw new Error("série padrão ausente na fita demo");

    const nullHtml = renderToStaticMarkup(<TickerTape items={[{ ...chaco, change_pct: null }]} />);
    expect(liOf(nullHtml, chaco.key)).toContain('data-direction="none"');

    const upHtml = renderToStaticMarkup(<TickerTape items={[{ ...chaco, change_pct: 0.5 }]} />);
    expect(liOf(upHtml, chaco.key)).toContain('data-direction="up"');
    expect(liOf(upHtml, chaco.key)).toContain(" subiu");
  });
});

describe("TickerTape: estados e acessibilidade", () => {
  it("raiz pronta: região rotulada, data-state ready e nenhum aria-live", () => {
    const html = renderToStaticMarkup(<TickerTape items={demoTicker(NOW)} />);

    expect(html).toContain('role="region"');
    expect(html).toContain('aria-label="Fita de cotações"');
    expect(html).toContain('data-testid="pregao-ticker"');
    expect(html).toContain('data-state="ready"');
    expect(html).not.toContain("aria-live");
  });

  it("sem itens: data-state empty com a mensagem de vazio", () => {
    const html = renderToStaticMarkup(<TickerTape items={[]} />);

    expect(html).toContain('data-state="empty"');
    expect(html).toContain("Sem cotações na fita.");
    expect(html).not.toContain("pregao-ticker-item");
  });

  it("carregando tem precedência sobre os itens: data-state loading e aria-busy", () => {
    const html = renderToStaticMarkup(<TickerTape items={demoTicker(NOW)} loading />);

    expect(html).toContain('data-state="loading"');
    expect(html).toContain('aria-busy="true"');
    expect(html).toContain("Carregando…");
    expect(html).not.toContain("pregao-ticker-item");
  });
});

describe("tickerLabel", () => {
  it("junta par, casa e taxa formatada pelo moeda cotada", () => {
    const item = itemOf(demoTicker(NOW), "chaco");
    const label = tickerLabel({ ...item, pair: "USD/PYG", house: "Cambios Chaco", mid: 7335 });

    expect(label).toBe(`USD/PYG Cambios Chaco ${formatRate(7335, "PYG")}`);
  });

  it("usa quatro casas para pares com BRL cotado", () => {
    const item = itemOf(demoTicker(NOW), "nomad");
    const label = tickerLabel({ ...item, pair: "USD/BRL", house: "Nomad", mid: 5.43 });

    expect(label).toBe(`USD/BRL Nomad ${formatRate(5.43, "BRL")}`);
  });

  it("mid nulo vira travessão", () => {
    const item = itemOf(demoTicker(NOW), "chaco");
    const label = tickerLabel({ ...item, pair: "USD/PYG", house: "Cambios Chaco", mid: null });

    expect(label).toBe("USD/PYG Cambios Chaco —");
  });
});
