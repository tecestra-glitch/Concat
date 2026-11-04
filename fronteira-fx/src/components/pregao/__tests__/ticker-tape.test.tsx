import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { TapePauseButton, TickerTape, tickerLabel } from "@/components/pregao/ticker-tape";
import { formatRate } from "@/lib/format";
import { DEFAULT_SERIES_KEY, demoTicker } from "@/lib/pregao/demo";
import type { TickerItem } from "@/lib/pregao/types";

const NOW = new Date(Date.UTC(2026, 10, 2, 12));

const countOf = (html: string, needle: string): number => html.split(needle).length - 1;

/** Todos os `<li>` da fita, na ordem do HTML (originais e cópias). */
const listItems = (html: string): string[] => html.match(/<li\b[^>]*>[\s\S]*?<\/li>/g) ?? [];

/** `<li>` de uma série: a original (`dup = false`) ou a cópia de laço (`dup = true`). */
function liOf(html: string, key: string, dup = false): string {
  const found = listItems(html).find((li) => li.includes(`data-key="${key}"`) && li.includes('data-dup="true"') === dup);
  if (!found) throw new Error(`item ${key} (dup=${dup}) não encontrado`);
  return found;
}

function itemOf(items: TickerItem[], sourceId: string): TickerItem {
  const found = items.find((i) => i.source_id === sourceId);
  if (!found) throw new Error(`casa ${sourceId} não encontrada na fita demo`);
  return found;
}

describe("TickerTape: laço contínuo", () => {
  it("renderiza cada item duas vezes e marca a cópia como aria-hidden e data-dup", () => {
    const items = demoTicker(NOW);
    const html = renderToStaticMarkup(<TickerTape items={items} />);

    expect(countOf(html, 'data-testid="pregao-ticker-item"')).toBe(2 * items.length);
    expect(countOf(html, 'data-dup="true"')).toBe(items.length);

    const copies = listItems(html).filter((li) => li.includes('data-dup="true"'));
    expect(copies).toHaveLength(items.length);
    for (const li of copies) {
      expect(li).toContain('aria-hidden="true"');
      expect(li).toContain("motion-reduce:hidden");
    }
  });
});

describe("TickerTape: itens", () => {
  it("referência é texto com ≈ e selo, sem botão", () => {
    const items = demoTicker(NOW);
    const bcp = itemOf(items, "bcp");
    const html = renderToStaticMarkup(<TickerTape items={items} onSelect={() => {}} />);
    const li = liOf(html, bcp.key);

    expect(li).toContain("≈ ");
    expect(li).toContain("pregao-reference-badge");
    expect(li).not.toContain("<button");
  });

  it("casa com onSelect é botão com aria-label igual a tickerLabel", () => {
    const items = demoTicker(NOW);
    const chaco = items.find((i) => i.key === DEFAULT_SERIES_KEY);
    if (!chaco) throw new Error("série padrão ausente na fita demo");
    const html = renderToStaticMarkup(<TickerTape items={items} onSelect={() => {}} />);
    const li = liOf(html, chaco.key);

    expect(li).toContain("<button");
    expect(li).toContain(`aria-label="${tickerLabel(chaco)}"`);
  });

  it("botões da cópia de laço ficam fora da ordem de tabulação", () => {
    const items = demoTicker(NOW);
    const chaco = items.find((i) => i.key === DEFAULT_SERIES_KEY);
    if (!chaco) throw new Error("série padrão ausente na fita demo");
    const html = renderToStaticMarkup(<TickerTape items={items} onSelect={() => {}} />);
    const copy = liOf(html, chaco.key, true);

    expect(copy).toContain("<button");
    expect(copy).toContain('tabindex="-1"');
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

  it("trilho usa a animação CSS, a duração padrão e a queda para lista estática", () => {
    const html = renderToStaticMarkup(<TickerTape items={demoTicker(NOW)} />);

    expect(html).toContain("pregao-marquee");
    expect(html).toContain("motion-reduce:animate-none");
    expect(html).toContain("--tape-duration:40s");
  });

  it("durationS substitui a duração padrão", () => {
    const html = renderToStaticMarkup(<TickerTape items={demoTicker(NOW)} durationS={25} />);

    expect(html).toContain("--tape-duration:25s");
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

describe("TickerTape: botão de pausa (WCAG 2.2.2, toque sem hover)", () => {
  it("sem onPausedChange não há botão", () => {
    const html = renderToStaticMarkup(<TickerTape items={demoTicker(NOW)} />);
    expect(html).not.toContain("pregao-ticker-pause");
  });

  it("rodando: botão 'Pausar fita' com aria-pressed=false; a lista não leva a pausa", () => {
    const html = renderToStaticMarkup(<TickerTape items={demoTicker(NOW)} onPausedChange={() => {}} />);
    const button = html.match(/<button[^>]*data-testid="pregao-ticker-pause"[^>]*>[\s\S]*?<\/button>/)?.[0] ?? "";
    expect(button).toContain('aria-pressed="false"');
    expect(button).toContain("Pausar fita");
    expect(button).toContain("motion-reduce:hidden");
    const ul = html.match(/<ul\b[^>]*>/)?.[0] ?? "";
    expect(ul).not.toContain("[animation-play-state:paused]");
    expect(ul).not.toContain("data-paused");
  });

  it("pausada: o rótulo continua 'Pausar fita' (constante) com aria-pressed=true e a lista para", () => {
    const html = renderToStaticMarkup(<TickerTape items={demoTicker(NOW)} paused onPausedChange={() => {}} />);
    const button = html.match(/<button[^>]*data-testid="pregao-ticker-pause"[^>]*>[\s\S]*?<\/button>/)?.[0] ?? "";
    expect(button).toContain('aria-pressed="true"');
    expect(button).toContain("Pausar fita");
    // Rótulo constante + aria-pressed: nunca "Retomar fita" no texto nem no nome.
    expect(html).not.toContain("Retomar fita");
    const ul = html.match(/<ul\b[^>]*>/)?.[0] ?? "";
    expect(ul).toContain("pregao-marquee");
    expect(ul).toContain("[animation-play-state:paused]");
    expect(ul).toContain('data-paused="true"');
  });

  it("o botão vem antes da lista no DOM (ordem de Tab = ordem visual, WCAG 2.4.3)", () => {
    const html = renderToStaticMarkup(<TickerTape items={demoTicker(NOW)} onPausedChange={() => {}} />);
    const button = html.indexOf('data-testid="pregao-ticker-pause"');
    const list = html.indexOf('<ul');
    expect(button).toBeGreaterThan(-1);
    expect(button).toBeLessThan(list);
  });

  it("o clique alterna o estado pedido ao handler", () => {
    const onPausedChange = vi.fn();
    const run = TapePauseButton({ paused: false, onPausedChange });
    (run.props as { onClick: () => void }).onClick();
    expect(onPausedChange).toHaveBeenLastCalledWith(true);
    const stopped = TapePauseButton({ paused: true, onPausedChange });
    (stopped.props as { onClick: () => void }).onClick();
    expect(onPausedChange).toHaveBeenLastCalledWith(false);
  });
});
