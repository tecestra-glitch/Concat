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
  banner: ReactNode; // null = sem faixa; só md+ (no celular a faixa global do app já avisa)
  ticker: ReactNode;
  controls: ReactNode; // seletor de par: vale para todas as abas
  timeframe: ReactNode; // TimeframeBar: no celular só na aba Gráfico
  indicators: ReactNode; // IndicatorToggles: no celular só na aba Gráfico
  stats: ReactNode;
  chart: ReactNode;
  book: ReactNode; // BookLadder
  bookExtra: ReactNode; // SpreadHeatmap + CrossRateCard: aba Livro no celular, sob o gráfico em lg+
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
  timeframe,
  indicators,
  stats,
  chart,
  book,
  bookExtra,
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
      {/* No celular a nota repetiria a faixa global de demonstração e empurraria as abas para baixo. */}
      {banner != null && (
        <div data-testid="pregao-banner" className="max-md:hidden">
          {banner}
        </div>
      )}

      <section aria-labelledby="pregao-h-fita">
        <h3 id="pregao-h-fita" className="sr-only">
          Fita
        </h3>
        {ticker}
      </section>

      {/*
        Controles, sessão e painéis numa grade só (trilhas explícitas; `items-start` impede que um painel estique
        até a altura do vizinho). Nenhuma coluna fica com vão ao lado do livro:
        - lg (2 colunas): esquerda = controles, gráfico, mapa + cruzado; direita = sessão, livro; "Últimas" na
          linha 5, nas duas colunas. A sessão ocupa as linhas 1–2 (a linha 1 fica com a altura dos controles, sem
          vão acima do resumo) e o gráfico atravessa a linha `1fr` (3): a sobra do livro vai só para ela.
        - xl (3 colunas): esquerda = controles (até a coluna 2), gráfico, mapa + cruzado; meio = livro; direita =
          sessão e "Últimas", empilhadas num bloco que vai da linha 1 à última e estica até o fim da grade.
          "Últimas" não pede altura (`contain: size`): ela ocupa o que sobra ao lado do livro, com rolagem própria.
        Abaixo de xl o bloco da direita é `contents` e cada filho é item da grade.
      */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_21rem] lg:grid-rows-[auto_auto_1fr_auto_auto] lg:items-start xl:grid-cols-[minmax(0,1fr)_21rem_18rem] xl:grid-rows-[auto_auto_1fr]">
        {/* Fica abaixo do cabeçalho fixo do app (h-14) ao rolar; z abaixo do cabeçalho (z-30). Vem antes dos controles:
            no celular as abas ficam na primeira metade da tela, logo depois da fita e da sessão. */}
        <div role="tablist" aria-label="Seções do pregão" data-testid="pregao-tabs" onKeyDown={onTablistKeyDown} className="sticky top-14 z-20 flex gap-1 bg-background py-1 md:hidden">
          {MOBILE_TABS.map(({ id, label }) => (
            <button
              key={id}
              type="button"
              role="tab"
              id={`pregao-tab-${id}`}
              aria-selected={id === tab}
              aria-controls={id === "livro" ? "pregao-panel-livro pregao-panel-livro-extra" : `pregao-panel-${id}`}
              tabIndex={id === tab ? 0 : -1}
              className={cn("h-10 flex-1 rounded-md text-sm", id === tab ? "bg-surface-2 text-foreground" : "text-muted")}
              onClick={() => setTab(id)}
            >
              {label}
            </button>
          ))}
        </div>

        <section aria-labelledby="pregao-h-controles" className="min-w-0 lg:col-start-1 lg:row-start-1 xl:col-end-3">
          <h3 id="pregao-h-controles" className="sr-only">
            Controles
          </h3>
          {/* Intervalo e indicadores só valem para o gráfico: no celular aparecem só na aba Gráfico. O par vale para
              todas as abas e, no celular, vem primeiro, logo abaixo das abas. Em md+ a ordem é intervalo, par,
              indicadores numa linha só (`contents` não cria caixa: os três ficam na mesma linha flexível). */}
          <div className="flex flex-wrap items-center gap-2">
            <div data-testid="pregao-controls-tf" className={cn("contents", tab !== "grafico" && "max-md:hidden")}>
              {timeframe}
            </div>
            <div data-testid="pregao-controls-pair" className="max-md:order-first">
              {controls}
            </div>
            <div data-testid="pregao-controls-ind" className={cn("contents", tab !== "grafico" && "max-md:hidden")}>
              {indicators}
            </div>
          </div>
        </section>

        <div
          id="pregao-panel-grafico"
          role="tabpanel"
          aria-labelledby="pregao-tab-grafico"
          className={cn(
            "grid grid-cols-1 content-start gap-3 min-w-0 lg:col-start-1 lg:row-span-2 lg:row-start-2 xl:row-span-1",
            tab !== "grafico" && "max-md:hidden",
          )}
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
          role="tabpanel"
          aria-labelledby="pregao-tab-livro"
          className={cn("min-w-0 lg:col-start-2 lg:row-span-2 lg:row-start-3 xl:row-start-2", tab !== "livro" && "max-md:hidden")}
        >
          <h3 id="pregao-h-livro" className="text-sm font-medium">
            Livro de casas
          </h3>
          {book}
        </section>

        {/* Mapa de spread e cruzado: aba Livro no celular; em lg+ sob o gráfico, ao lado do livro. */}
        <div
          id="pregao-panel-livro-extra"
          role="tabpanel"
          aria-labelledby="pregao-tab-livro"
          data-testid="pregao-book-extra"
          className={cn("min-w-0 lg:col-start-1 lg:row-start-4 xl:row-start-3", tab !== "livro" && "max-md:hidden")}
        >
          {bookExtra}
        </div>

        <div data-testid="pregao-side" className="contents xl:col-start-3 xl:row-span-3 xl:row-start-1 xl:flex xl:min-w-0 xl:flex-col xl:gap-4 xl:self-stretch">
          <section aria-labelledby="pregao-h-sessao" className="min-w-0 max-lg:order-first lg:col-start-2 lg:row-span-2 lg:row-start-1">
            <h3 id="pregao-h-sessao" className="text-sm font-medium">
              Sessão
            </h3>
            {clocks}
          </section>

          <section
            id="pregao-panel-ultimas"
            role="tabpanel"
            aria-labelledby="pregao-tab-ultimas"
            className={cn(
              "min-w-0 lg:col-span-2 lg:col-start-1 lg:row-start-5 xl:flex xl:min-h-[18rem] xl:flex-1 xl:flex-col xl:[contain:size]",
              tab !== "ultimas" && "max-md:hidden",
            )}
          >
            <h3 id="pregao-h-ultimas" className="text-sm font-medium">
              Últimas atualizações
            </h3>
            {prints}
          </section>
        </div>
      </div>

      <section id="pregao-panel-lista" role="tabpanel" aria-labelledby="pregao-tab-lista" className={cn("min-w-0", tab !== "lista" && "max-md:hidden")}>
        <h3 id="pregao-h-lista" className="text-sm font-medium">
          Lista
        </h3>
        {watchlist}
      </section>
    </div>
  );
}
