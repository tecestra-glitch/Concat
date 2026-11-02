import { readFileSync } from "node:fs";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { Pregao, remotePanel } from "@/components/pregao/pregao";
import { SettingsProvider } from "@/lib/settings";

const SRC = new URL("../pregao.tsx", import.meta.url).pathname;

/** Render do servidor: `useNow()` vale 0 e o modo resolvido é demo (backend ainda desconhecido). */
function serverHtml(): string {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return renderToStaticMarkup(
    <QueryClientProvider client={qc}>
      <SettingsProvider>
        <Pregao />
      </SettingsProvider>
    </QueryClientProvider>,
  );
}

describe("Pregao (container da integração, §24.4)", () => {
  const html = serverHtml();

  it("raiz com o modo, um só h2 «Pregão» e o botão de atalhos", () => {
    expect(html).toContain('data-testid="pregao-root"');
    expect(html).toContain('data-mode="demo"');
    expect(html.match(/<h2[ >]/g)).toHaveLength(1);
    expect(html).toMatch(/<h2[^>]*>Pregão<\/h2>/);
    expect(html).toContain("Cotações publicadas pelas casas de câmbio. Referências do BCP só para comparar.");
    expect(html).toMatch(/Atalhos[\s\S]*?<kbd[^>]*>\?<\/kbd>/);
  });

  it("modo demo: nota de demonstração no slot do banner", () => {
    expect(html).toContain('data-testid="pregao-banner"');
    expect(html).toContain('data-testid="pregao-demo-note"');
    expect(html).toContain("Demonstração: velas, livro e atualizações são gerados localmente e não refletem o mercado.");
  });

  it("monta o layout com todos os blocos, em carregando enquanto o relógio não começou", () => {
    expect(html).toContain('data-testid="pregao-layout"');
    for (const id of ["pregao-ticker", "pregao-stats", "pregao-chart", "pregao-book", "pregao-heatmap", "pregao-prints", "pregao-watchlist"]) {
      expect(html).toMatch(new RegExp(`data-testid="${id}"[^>]*data-state="loading"|data-state="loading"[^>]*data-testid="${id}"`));
    }
    for (const id of ["pregao-timeframe", "pregao-pair", "pregao-indicators", "pregao-clock", "pregao-market-status", "pregao-cross", "pregao-tabs"]) {
      expect(html).toContain(`data-testid="${id}"`);
    }
  });

  it("controles começam nas preferências padrão (1 h, par USD/PYG)", () => {
    expect(html).toMatch(/data-tf="1h"[^>]*aria-checked="true"|aria-checked="true"[^>]*data-tf="1h"/);
    expect(html).toMatch(/data-pair="USD\/PYG"[^>]*aria-checked="true"|aria-checked="true"[^>]*data-pair="USD\/PYG"/);
  });

  it("grades do layout têm trilha minmax(0,1fr) (grid-cols-1): a fita w-max e o canvas não alargam a página", () => {
    const grids = [...html.matchAll(/<div[^>]*class="(grid [^"]*)"/g)].map((m) => m[1]);
    // raiz do layout e pilha do livro; a grade única de controles, sessão e painéis (até lg); o painel do gráfico
    expect(grids.filter((c) => c === "grid grid-cols-1 gap-4")).toHaveLength(2);
    expect(grids.filter((c) => /^grid grid-cols-1 gap-(3|4) lg:grid-cols-\[minmax\(0,1fr\)_20rem\]/.test(c))).toHaveLength(1);
    // painel do gráfico: as linhas não esticam até a altura do livro (sem vão entre resumo e gráfico)
    expect(grids.some((c) => c.startsWith("grid grid-cols-1 content-start gap-3 min-w-0"))).toBe(true);
    expect(html).not.toContain('class="grid gap-4');
  });

  it("mapa de spread tem seção e título próprios dentro do livro", () => {
    expect(html).toMatch(/<section aria-labelledby="pregao-h-mapa"[^>]*>\s*<h3 id="pregao-h-mapa"[^>]*>Mapa de spread<\/h3>/);
  });

  it("regras de fonte: sem Date.now no render, sem efeitos, sem hex, sem NEXT_PUBLIC_", () => {
    const src = readFileSync(SRC, "utf8");
    expect(src.startsWith('"use client";')).toBe(true);
    expect(src).not.toMatch(/Date\.now\(|new Date\(\)/);
    expect(src).not.toMatch(/useEffect|useLayoutEffect/);
    expect(src).not.toMatch(/#[0-9a-fA-F]{3,8}\b/);
    expect(src).not.toContain("NEXT_PUBLIC_");
    expect(src).toMatch(/dynamic\(\s*\(\) => import\("@\/components\/pregao\/candle-chart"\)/);
  });
});

describe("remotePanel (resumo e gráfico dependem das cotações)", () => {
  const idle = { isLoading: false, data: undefined, error: null };
  const quotesErr = new Error("cotações");

  it("enquanto as cotações carregam o painel carrega, mesmo com a consulta própria desligada", () => {
    expect(remotePanel(idle, { loading: true, error: null })).toEqual({ loading: true, error: null, retryUpstream: false });
  });

  it("falha das cotações sem dados próprios vira erro do painel, com nova tentativa nas cotações", () => {
    expect(remotePanel(idle, { loading: false, error: quotesErr })).toEqual({ loading: false, error: quotesErr, retryUpstream: true });
  });

  it("erro próprio vence; com dados já mostrados não há erro", () => {
    const own = new Error("velas");
    expect(remotePanel({ ...idle, error: own }, { loading: false, error: quotesErr })).toEqual({ loading: false, error: own, retryUpstream: false });
    expect(remotePanel({ ...idle, data: {}, error: own }, { loading: false, error: null })).toEqual({ loading: false, error: null, retryUpstream: false });
    expect(remotePanel({ ...idle, isLoading: true }, { loading: false, error: null }).loading).toBe(true);
  });
});
