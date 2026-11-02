"use client";
import { useState, type KeyboardEvent, type ReactElement, type ReactNode } from "react";
import { cn } from "@/lib/utils";

export type PregaoMobileTab = "grafico" | "livro" | "lista" | "ultimas";

export const MOBILE_TABS: readonly { id: PregaoMobileTab; label: string }[] = [
  { id: "grafico", label: "Gráfico" },
  { id: "livro", label: "Livro" },
  { id: "lista", label: "Lista" },
  { id: "ultimas", label: "Últimas" },
];

/** Próxima aba para uma tecla de navegação: setas cíclicas, Home e End. Outras teclas → `null`. */
export function nextTab(current: PregaoMobileTab, key: string): PregaoMobileTab | null {
  const ids = MOBILE_TABS.map((t) => t.id);
  const i = ids.indexOf(current);
  switch (key) {
    case "ArrowRight":
      return ids[(i + 1) % ids.length];
    case "ArrowLeft":
      return ids[(i - 1 + ids.length) % ids.length];
    case "Home":
      return ids[0];
    case "End":
      return ids[ids.length - 1];
    default:
      return null;
  }
}

export interface PregaoLayoutProps {
  banner: ReactNode; // null = sem faixa
  ticker: ReactNode;
  controls: ReactNode;
  stats: ReactNode;
  chart: ReactNode;
  book: ReactNode; // BookLadder + SpreadHeatmap + CrossRateCard, empilhados pelo container
  prints: ReactNode;
  watchlist: ReactNode;
  clocks: ReactNode; // SessionClock + MarketStatus
  defaultTab?: PregaoMobileTab; // padrão "grafico"
  className?: string;
}

/**
 * Grade da tela de pregão. Uma única árvore DOM para todas as larguras: em `< md` os painéis não ativos
 * ficam ocultos por `max-md:hidden` (continuam montados), e as abas aparecem; em `md+` o tablist some.
 * Toda grade tem trilha explícita `minmax(0, 1fr)` (`grid-cols-1` abaixo de `lg`): uma trilha implícita
 * `auto` cresceria até o conteúdo mais largo (a fita `w-max`, o canvas do gráfico) e alargaria a página.
 */
export function PregaoLayout({
  banner,
  ticker,
  controls,
  stats,
  chart,
  book,
  prints,
  watchlist,
  clocks,
  defaultTab,
  className,
}: PregaoLayoutProps): ReactElement {
  const [tab, setTab] = useState<PregaoMobileTab>(defaultTab ?? "grafico");

  function onTablistKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    const next = nextTab(tab, e.key);
    if (next === null) return;
    e.preventDefault();
    setTab(next);
    e.currentTarget.querySelector<HTMLButtonElement>(`#pregao-tab-${next}`)?.focus();
  }

  return (
    <div data-testid="pregao-layout" data-mobile-tab={tab} className={cn("grid grid-cols-1 gap-4", className)}>
      {banner != null && <div data-testid="pregao-banner">{banner}</div>}

      <section aria-labelledby="pregao-h-fita">
        <h3 id="pregao-h-fita" className="sr-only">
          Fita
        </h3>
        {ticker}
      </section>

      {/*
        Controles, sessão e painéis numa grade só. Em lg+ a sessão ocupa as linhas 1–2 da coluna da direita
        e o painel do gráfico começa na linha 2: a linha 1 fica com a altura dos controles e a coluna esquerda
        não herda a altura da sessão (sem vão entre os controles e o resumo). A linha 2 só existe para a
        sobra da sessão; a linha `1fr` absorve a altura dos painéis que a atravessam (gráfico e, em xl, livro),
        senão o algoritmo da grade repartiria essa altura com a linha 2 e empurraria "Últimas" para baixo.
        `items-start` impede que um painel estique até a altura do vizinho.
      */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_20rem] lg:grid-rows-[auto_auto_1fr_auto] lg:items-start xl:grid-cols-[minmax(0,1fr)_20rem_18rem] xl:grid-rows-[auto_auto_1fr]">
        <section aria-labelledby="pregao-h-controles" className="min-w-0 lg:col-start-1 lg:row-start-1 xl:col-end-3">
          <h3 id="pregao-h-controles" className="sr-only">
            Controles
          </h3>
          {controls}
        </section>
        <section aria-labelledby="pregao-h-sessao" className="min-w-0 max-md:order-first lg:col-start-2 lg:row-span-2 lg:row-start-1 xl:col-start-3">
          <h3 id="pregao-h-sessao" className="text-sm font-medium">
            Sessão
          </h3>
          {clocks}
        </section>

        <div role="tablist" aria-label="Seções do pregão" data-testid="pregao-tabs" onKeyDown={onTablistKeyDown} className="sticky top-0 z-10 flex gap-1 bg-background py-1 md:hidden">
          {MOBILE_TABS.map(({ id, label }) => (
            <button
              key={id}
              type="button"
              role="tab"
              id={`pregao-tab-${id}`}
              aria-selected={id === tab}
              aria-controls={`pregao-panel-${id}`}
              tabIndex={id === tab ? 0 : -1}
              className={cn("h-10 flex-1 rounded-md text-sm", id === tab ? "bg-surface-2 text-foreground" : "text-muted")}
              onClick={() => setTab(id)}
            >
              {label}
            </button>
          ))}
        </div>

        <div
          id="pregao-panel-grafico"
          className={cn("grid grid-cols-1 content-start gap-3 min-w-0 lg:col-start-1 lg:row-span-2 lg:row-start-2", tab !== "grafico" && "max-md:hidden")}
        >
          <section aria-labelledby="pregao-h-resumo">
            <h3 id="pregao-h-resumo" className="text-sm font-medium">
              Resumo da sessão
            </h3>
            {stats}
          </section>
          <section aria-labelledby="pregao-h-grafico">
            <h3 id="pregao-h-grafico" className="text-sm font-medium">
              Gráfico
            </h3>
            <div className="h-[280px] md:h-[360px] xl:h-[420px]">{chart}</div>
          </section>
        </div>

        <section
          id="pregao-panel-livro"
          aria-labelledby="pregao-h-livro"
          className={cn("min-w-0 lg:col-start-2 lg:row-start-3 xl:row-span-2 xl:row-start-2", tab !== "livro" && "max-md:hidden")}
        >
          <h3 id="pregao-h-livro" className="text-sm font-medium">
            Livro de casas
          </h3>
          {book}
        </section>

        <section
          id="pregao-panel-ultimas"
          aria-labelledby="pregao-h-ultimas"
          className={cn("min-w-0 lg:col-span-2 lg:col-start-1 lg:row-start-4 xl:col-span-1 xl:col-start-3 xl:row-start-3", tab !== "ultimas" && "max-md:hidden")}
        >
          <h3 id="pregao-h-ultimas" className="text-sm font-medium">
            Últimas atualizações
          </h3>
          {prints}
        </section>
      </div>

      <section id="pregao-panel-lista" aria-labelledby="pregao-h-lista" className={cn("min-w-0", tab !== "lista" && "max-md:hidden")}>
        <h3 id="pregao-h-lista" className="text-sm font-medium">
          Lista
        </h3>
        {watchlist}
      </section>
    </div>
  );
}
