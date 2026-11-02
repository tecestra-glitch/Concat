import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { LatestPrints, type LatestPrintsProps, printTime } from "@/components/pregao/latest-prints";
import { demoPrints } from "@/lib/pregao/demo";
import type { Print } from "@/lib/pregao/types";

const NOW = new Date(Date.UTC(2026, 10, 2, 12));
const prints: Print[] = demoPrints(NOW, 10);

function render(props: Partial<LatestPrintsProps> & Pick<LatestPrintsProps, "prints">): string {
  return renderToStaticMarkup(createElement(LatestPrints, props));
}

const rowCount = (html: string) => html.match(/data-testid="pregao-print-row"/g)?.length ?? 0;
const sourceOf = (rel: string) => readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf8");

describe("LatestPrints: estrutura e rótulo", () => {
  it("mostra o aviso de que não são negócios fechados, a raiz e uma linha por print", () => {
    const html = render({ prints });
    expect(html).toContain("Não são negócios fechados.");
    expect(html).toContain('data-testid="pregao-prints"');
    expect(html).toContain('data-state="ready"');
    expect(rowCount(html)).toBe(10);
    expect(html).toContain("pregao-flash");
    expect(html).toContain('data-mode="demo"');
  });

  it("respeita limit", () => {
    expect(rowCount(render({ prints, limit: 3 }))).toBe(3);
  });

  it("não tem aria-live e não usa palavras proibidas da interface", () => {
    const html = render({ prints });
    expect(html).not.toContain("aria-live");
    expect(html).not.toMatch(/\b(trade|ordem|executar)\b/i);
  });

  it("linhas têm hora, casa, par, compra, venda e variação com seta e texto para leitor de tela", () => {
    const html = render({ prints, limit: 1 });
    expect(html).toContain("<time");
    expect(html).toContain('data-testid="pregao-delta"');
    expect(html).toContain('class="sr-only"');
    expect(html).toContain("max-sm:hidden");
  });
});

describe("printTime", () => {
  it("formata a hora em America/Asuncion (UTC−3 em novembro)", () => {
    expect(printTime("2026-11-02T15:04:05Z")).toBe("12:04:05");
  });
});

describe("LatestPrints: estados", () => {
  it("lista vazia vira data-state=empty com a mensagem exata", () => {
    const html = render({ prints: [] });
    expect(html).toContain('data-state="empty"');
    expect(html).toContain("Nenhuma atualização ainda.");
    expect(html).not.toContain("pregao-print-row");
  });

  it("erro vira role=alert com a mensagem exata e botão só quando há onRetry", () => {
    const err = new Error("HTTP 503");
    const withRetry = render({ prints: [], error: err, onRetry: () => {} });
    expect(withRetry).toContain('data-state="error"');
    expect(withRetry).toContain('role="alert"');
    expect(withRetry).toContain("Não foi possível carregar as atualizações.");
    expect(withRetry).toContain("HTTP 503");
    expect(withRetry).toContain("Tentar de novo");

    const noRetry = render({ prints: [], error: err });
    expect(noRetry).not.toContain("Tentar de novo");
  });

  it("carregando mostra skeleton com aria-busy e texto sr-only", () => {
    const html = render({ prints, loading: true });
    expect(html).toContain('data-state="loading"');
    expect(html).toContain('aria-busy="true"');
    expect(html).toContain("Carregando…");
    expect(html).not.toContain("pregao-print-row");
  });
});

describe("LatestPrints: linhas especiais", () => {
  const base = prints[0];

  it("referência não é selecionável, leva o selo de referência e prefixo ≈ no preço", () => {
    const ref: Print = { ...base, source_id: "bcp", house: "BCP (referência)", kind: "market_reference" };
    const html = render({ prints: [ref], onSelect: () => {} });
    expect(html).toContain('data-testid="pregao-reference-badge"');
    expect(html).toContain("≈ ");
    expect(html).not.toContain("<button");
  });

  it("casa executável é um botão quando onSelect é passado", () => {
    const html = render({ prints: [base], onSelect: () => {} });
    expect(html).toContain('<button type="button"');
    expect(html).toContain(base.house);
  });

  it("cotação incompleta mostra o aviso 'incompleta'", () => {
    const html = render({ prints: [{ ...base, incomplete: true, buy: null }] });
    expect(html).toContain("incompleta");
  });
});

describe("arquivos de F8: regras de hooks e estado", () => {
  it("latest-prints.tsx não usa useRef, useState nem useEffect", () => {
    expect(sourceOf("../latest-prints.tsx")).not.toMatch(/useRef\(|useState\(|useEffect\(/);
  });

  it("use-prints.ts não usa setState nem useState", () => {
    expect(sourceOf("../../../lib/pregao/use-prints.ts")).not.toMatch(/setState|useState\(/);
  });
});
