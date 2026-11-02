import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { CrossRateCard, crossState, fmtPyg, type CrossRateCardProps } from "@/components/pregao/cross-rate-card";
import type { Leg } from "@/lib/pregao/cross";

const now = Date.UTC(2026, 10, 2, 12);
const at = "2026-11-02T11:50:00Z";
const old = "2026-11-01T11:00:00Z";

const usdPyg: Leg = { buy: "5905", sell: "5975", captured_at: at };
const usdBrl: Leg = { buy: "5.40", sell: "5.46", captured_at: at };
const direct: Leg = { buy: "1092", sell: "1112", captured_at: at };

function render(p: Partial<CrossRateCardProps> = {}): string {
  const props: CrossRateCardProps = { house: "Cambios Chaco", usdPyg, usdBrl, direct, now, ...p };
  return renderToStaticMarkup(createElement(CrossRateCard, props));
}

describe("CrossRateCard — pronto", () => {
  it("mostra implícito, direto, diferenças e o aviso informativo", () => {
    const html = render();
    expect(html).toContain('data-testid="pregao-cross"');
    expect(html).toContain('data-state="ready"');
    expect(html).toContain("informativo, não executável");
    expect(html).toContain("BRL/PYG cruzado via USD");
    expect(html).toContain("1.082");
    expect(html).toContain("1.106");
    expect(html).toContain("1.092");
    expect(html).toContain("1.112");
    expect(html.split('data-testid="pregao-delta"').length - 1).toBe(2);
    expect(html).not.toContain("incompleto");
  });

  it("mostra 'não publicado' no direto quando a casa não publica o par", () => {
    expect(render({ direct: null })).toContain("não publicado");
  });

  it("fmtPyg arredonda o implícito para inteiro e trata nulo como travessão", () => {
    expect(fmtPyg("1081.5018315")).toBe("1.082");
    expect(fmtPyg(null)).toBe("—");
  });
});

describe("CrossRateCard — estados", () => {
  it("sem Venda em USD/BRL mostra o aviso 'incompleto' e travessão no lado nulo", () => {
    const html = render({ usdBrl: { buy: "5.40", sell: null, captured_at: at } });
    expect(html).toContain("incompleto");
    expect(html).toContain("—");
  });

  it("sem uma das pernas em USD fica vazio e explica", () => {
    const html = render({ usdBrl: null });
    expect(html).toContain('data-state="empty"');
    expect(html).toContain("Esta casa não publica as duas pernas em USD.");
    expect(crossState({ usdPyg, usdBrl: null })).toBe("empty");
    expect(crossState({ usdPyg, usdBrl })).toBe("ready");
  });

  it("perna de 25 h com now > 0 mostra 'pernas antigas'", () => {
    const html = render({ usdBrl: { buy: "5.40", sell: "5.46", captured_at: old } });
    expect(html).toContain("pernas antigas");
  });

  it("com now = 0 nunca mostra 'pernas antigas' e usa o rodapé sem idade", () => {
    const html = render({ now: 0, usdBrl: { buy: "5.40", sell: "5.46", captured_at: old } });
    expect(html).not.toContain("pernas antigas");
    expect(html).toContain("cotações publicadas pela casa");
  });
});

describe("CrossRateCard — cor", () => {
  it("cor de alta/baixa só aparece dentro das variações", () => {
    const full = render();
    expect(full).toContain("text-gain");
    const outside = full.replace(/<span[^>]*data-testid="pregao-delta"[\s\S]*?<\/span><\/span>/g, "");
    expect(outside).not.toMatch(/text-gain|text-loss/);
  });
});
