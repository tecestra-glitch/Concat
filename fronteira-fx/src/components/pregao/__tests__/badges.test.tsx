import { readFileSync } from "node:fs";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { AgioBadge } from "@/components/pregao/agio-badge";
import { Delta } from "@/components/pregao/delta";
import { ReferenceBadge } from "@/components/pregao/reference-badge";

/** U+2212, o sinal de menos tipográfico de `formatPercent` e `deltaText`. */
const MINUS = "−";

/** Texto visível e sr-only, sem marcação: confere vírgulas e sinais sem casar atributos de SVG. */
const textOf = (html: string): string => html.replace(/<[^>]*>/g, "");

/** Fonte de um arquivo de componente, lida do disco (testes de fonte, §10.1 item 4 e §10.2 item 6). */
const sourceOf = (name: string): string => readFileSync(new URL(`../${name}`, import.meta.url), "utf8");

describe("Delta", () => {
  it("alta: seta aria-hidden, cor de ganho, sinal, texto sr-only e title com o mesmo texto", () => {
    const html = renderToStaticMarkup(<Delta value={0.84} />);
    expect(html).toContain('data-direction="up"');
    expect(html).toContain("text-gain");
    expect(html).toContain("+0,84");
    expect(html).toContain("%");
    expect(html).toContain('class="sr-only"> subiu');
    expect(html).toContain('title="+0,84 % subiu"');
    expect(html).toContain('aria-hidden="true"');
  });

  it("baixa: sinal U+2212 em formatPercent, cor de perda e texto 'caiu'", () => {
    const html = renderToStaticMarkup(<Delta value={-1} />);
    expect(html).toContain('data-direction="down"');
    expect(html).toContain("text-loss");
    expect(html).toContain(`${MINUS}1,00 %`);
    expect(html).toContain('class="sr-only"> caiu');
  });

  it("zero: direção flat em cor neutra e texto 'estável'", () => {
    const html = renderToStaticMarkup(<Delta value={0} />);
    expect(html).toContain('data-direction="flat"');
    expect(html).toContain("text-muted");
    expect(html).toContain('class="sr-only"> estável');
  });

  it("sem valor: traço, direção none e aviso 'sem variação disponível' no title e no sr-only", () => {
    const html = renderToStaticMarkup(<Delta value={null} />);
    expect(html).toContain('data-direction="none"');
    expect(html).toContain("—");
    expect(html).toContain("sem variação disponível");
    expect(html).toContain('title="— sem variação disponível"');
  });

  it("sem valor: um único '—' apagado, sem o ícone neutro; 0,00 % mantém o ícone", () => {
    const none = renderToStaticMarkup(<Delta value={null} />);
    expect(none).not.toContain("<svg");
    expect(none).toContain("text-muted");
    expect(textOf(none).replace(/sem variação disponível/, "").match(/—/g)).toHaveLength(1);
    const zero = renderToStaticMarkup(<Delta value={0} />);
    expect(zero).toContain("<svg");
    expect(textOf(zero)).toContain("0,00 %");
  });

  it("valor string não numérico é tratado como null", () => {
    const html = renderToStaticMarkup(<Delta value="abc" />);
    expect(html).toContain('data-direction="none"');
    expect(html).toContain("—");
  });

  it("kind abs em PYG: + explícito, sem casas decimais e sem vírgula no texto", () => {
    const html = renderToStaticMarkup(<Delta value="12" kind="abs" quote="PYG" />);
    expect(html).toContain("+12");
    expect(textOf(html)).not.toContain(",");
    expect(html).toContain('data-direction="up"');
  });

  it("kind abs em BRL: sinal U+2212 e quatro casas decimais", () => {
    const html = renderToStaticMarkup(<Delta value="-0.5" kind="abs" quote="BRL" />);
    expect(html).toContain(`${MINUS}0,5000`);
    expect(html).toContain('data-direction="down"');
  });
});

describe("AgioBadge", () => {
  it("ágio positivo: sinal +, 'acima da referência' e title com 'Ágio'", () => {
    const html = renderToStaticMarkup(<AgioBadge value={0.50868} />);
    expect(html).toContain("+0,51 %");
    expect(html).toContain("acima da referência");
    expect(html).toContain('data-testid="pregao-agio-badge"');
    expect(html).toContain('title="Ágio em relação à referência (BCP/dolarPy)"');
    expect(html).toContain('data-direction="up"');
  });

  it("ágio negativo: sinal U+2212 e 'abaixo da referência'", () => {
    const html = renderToStaticMarkup(<AgioBadge value={-0.66882} />);
    expect(html).toContain(`${MINUS}0,67 %`);
    expect(html).toContain("abaixo da referência");
    expect(html).toContain('data-direction="down"');
  });

  it("zero: 'igual à referência' e direção flat", () => {
    const html = renderToStaticMarkup(<AgioBadge value={0} />);
    expect(html).toContain("igual à referência");
    expect(html).toContain('data-direction="flat"');
  });

  it("sem referência: traço, 'sem referência' e direção none", () => {
    const html = renderToStaticMarkup(<AgioBadge value={null} />);
    expect(html).toContain("—");
    expect(html).toContain("sem referência");
    expect(html).toContain('data-direction="none"');
  });
});

describe("ReferenceBadge", () => {
  it("visível: texto 'Referência' fora de sr-only, aviso de não executável e borda tracejada", () => {
    const html = renderToStaticMarkup(<ReferenceBadge />);
    expect(html).toContain('data-testid="pregao-reference-badge"');
    expect(html).not.toMatch(/sr-only[^>]*>Referência/);
    expect(textOf(html)).toContain("Referência");
    expect(html).toContain("Não é executável");
    expect(html).toContain("border-dashed");
    expect(html).not.toContain("data-compact");
  });

  it("compacto: 'Referência' em sr-only, data-compact e fonte no fim do title", () => {
    const html = renderToStaticMarkup(<ReferenceBadge compact source="bcp" />);
    expect(html).toContain('data-compact="true"');
    expect(html).toContain('class="sr-only">Referência');
    expect(html).toMatch(/title="[^"]*Fonte: bcp\."/);
  });
});

describe("fonte dos selos e da variação", () => {
  const files = ["delta.tsx", "agio-badge.tsx", "reference-badge.tsx"];

  it("nenhum hexadecimal literal nem estilo inline de cor", () => {
    for (const f of files) {
      expect(sourceOf(f), f).not.toMatch(/#[0-9a-fA-F]{3,6}\b/);
      expect(sourceOf(f), f).not.toMatch(/style=\{\{\s*color/);
    }
  });

  it("selos de ágio e referência são neutros: nada de text-gain/text-loss", () => {
    for (const f of ["agio-badge.tsx", "reference-badge.tsx"]) {
      expect(sourceOf(f), f).not.toMatch(/text-(gain|loss)/);
    }
  });
});
