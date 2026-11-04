import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { PairSelector } from "@/components/pregao/pair-selector";
import { IndicatorToggles, INDICATOR_ITEMS } from "@/components/pregao/indicator-toggles";
import { rovingIndex, TimeframeBar } from "@/components/pregao/timeframe-bar";
import { INDICATOR_DEFAULTS, PAIRS } from "@/lib/pregao/types";

/** Abre todas as tags `<tag ...>` do markup, na ordem em que aparecem. */
function tagsOf(html: string, tag: string): string[] {
  return html.match(new RegExp(`<${tag}\\b[^>]*>`, "g")) ?? [];
}

/** Valor de um atributo dentro de uma tag, ou `null` quando ausente. */
function attr(tag: string, name: string): string | null {
  const m = tag.match(new RegExp(`\\s${name}="([^"]*)"`));
  return m ? m[1] : null;
}

describe("rovingIndex", () => {
  it("move ciclicamente com setas e vai ao início e ao fim com Home/End", () => {
    expect(rovingIndex(0, "ArrowRight", 4)).toBe(1);
    expect(rovingIndex(3, "ArrowRight", 4)).toBe(0);
    expect(rovingIndex(0, "ArrowLeft", 4)).toBe(3);
    expect(rovingIndex(2, "Home", 4)).toBe(0);
    expect(rovingIndex(0, "End", 4)).toBe(3);
    expect(rovingIndex(0, "a", 4)).toBeNull();
  });

  it("aceita ArrowDown e ArrowUp como avanço e recuo", () => {
    expect(rovingIndex(0, "ArrowDown", 4)).toBe(1);
    expect(rovingIndex(3, "ArrowDown", 4)).toBe(0);
    expect(rovingIndex(0, "ArrowUp", 4)).toBe(3);
  });
});

describe("TimeframeBar", () => {
  const html = renderToStaticMarkup(<TimeframeBar value="1h" onChange={() => {}} />);
  const buttons = tagsOf(html, "button");

  it("renderiza um radiogroup com um radio por intervalo", () => {
    expect(html).toContain('data-testid="pregao-timeframe"');
    expect(html).toContain('aria-label="Intervalo das velas"');
    expect(html).toContain('role="radiogroup"');
    expect(buttons).toHaveLength(4);
    for (const b of buttons) expect(attr(b, "role")).toBe("radio");
  });

  it("marca exatamente um intervalo e só ele entra na ordem de tabulação", () => {
    const checked = buttons.filter((b) => attr(b, "aria-checked") === "true");
    expect(checked).toHaveLength(1);
    expect(attr(checked[0], "data-tf")).toBe("1h");
    expect(attr(checked[0], "tabindex")).toBe("0");
    const others = buttons.filter((b) => attr(b, "data-tf") !== "1h");
    for (const b of others) expect(attr(b, "tabindex")).toBe("-1");
  });

  it("rotula cada intervalo com a tecla de atalho e mostra o texto curto", () => {
    expect(buttons.map((b) => attr(b, "aria-label"))).toEqual([
      "15 min (tecla 1)",
      "1 hora (tecla 2)",
      "4 horas (tecla 3)",
      "1 dia (tecla 4)",
    ]);
    for (const text of [">15m</button>", ">1h</button>", ">4h</button>", ">1d</button>"]) {
      expect(html).toContain(text);
    }
  });

  it("desabilita todos os botões quando disabled", () => {
    const off = renderToStaticMarkup(<TimeframeBar value="15m" onChange={() => {}} disabled />);
    const offButtons = tagsOf(off, "button");
    expect(offButtons).toHaveLength(4);
    for (const b of offButtons) expect(b).toContain('disabled=""');
  });
});

describe("PairSelector", () => {
  it("renderiza um radio por par com data-pair e o texto do par", () => {
    const html = renderToStaticMarkup(<PairSelector value="USD/PYG" onChange={() => {}} />);
    const buttons = tagsOf(html, "button");
    expect(buttons.map((b) => attr(b, "data-pair"))).toEqual(["USD/PYG", "BRL/PYG", "USD/BRL"]);
    // Cada opção tem bandeiras (SVG aria-hidden) e o nome do par em texto contínuo (spec §5b-b).
    const whole = html.match(/<button\b[\s\S]*?<\/button>/g) ?? [];
    expect(whole.map((b) => b.replace(/<[^>]+>/g, ""))).toEqual(["USD/PYG", "BRL/PYG", "USD/BRL"]);
    expect(html).toContain('role="radio"');
    expect(html).toContain('data-testid="pregao-pair"');
    expect(html).toContain('role="radiogroup"');
  });

  it("aceita a lista de pares por propriedade", () => {
    const html = renderToStaticMarkup(<PairSelector value="USD/PYG" pairs={["USD/PYG"]} onChange={() => {}} />);
    expect(tagsOf(html, "button")).toHaveLength(1);
  });

  it("usa PAIRS como lista padrão", () => {
    const html = renderToStaticMarkup(<PairSelector value="USD/PYG" onChange={() => {}} />);
    expect(tagsOf(html, "button")).toHaveLength(PAIRS.length);
  });

  it("desabilita todos os botões quando disabled", () => {
    const html = renderToStaticMarkup(<PairSelector value="USD/PYG" onChange={() => {}} disabled />);
    for (const b of tagsOf(html, "button")) expect(b).toContain('disabled=""');
  });
});

describe("IndicatorToggles", () => {
  const html = renderToStaticMarkup(
    <IndicatorToggles value={{ ...INDICATOR_DEFAULTS, sma: true }} onChange={() => {}} />,
  );
  const buttons = tagsOf(html, "button");
  const pressed = (id: string) => buttons.find((b) => attr(b, "data-indicator") === id) ?? "";

  it("renderiza uma toolbar com os indicadores na ordem definida", () => {
    expect(html).toContain('role="toolbar"');
    expect(html).toContain('aria-label="Indicadores"');
    expect(html).toContain('data-testid="pregao-indicators"');
    expect(buttons.map((b) => attr(b, "data-indicator"))).toEqual(INDICATOR_ITEMS.map((i) => i.id));
  });

  it("expõe aria-pressed conforme o estado de cada indicador", () => {
    expect(attr(pressed("sma"), "aria-pressed")).toBe("true");
    expect(attr(pressed("volume"), "aria-pressed")).toBe("true");
    expect(attr(pressed("ema"), "aria-pressed")).toBe("false");
    expect(attr(pressed("bollinger"), "aria-pressed")).toBe("false");
  });

  it("usa os rótulos e as dicas exatas da especificação", () => {
    expect(attr(pressed("sma"), "title")).toBe("Média simples de 20 velas");
    expect(html).toContain(">SMA 20</button>");
    expect(html).toContain(">EMA 9</button>");
    expect(html).toContain(">Bollinger</button>");
    expect(html).toContain("Nº de cotações");
    expect(html).not.toContain("Volume");
  });

  it("tem roving tabindex com foco inicial no primeiro indicador", () => {
    expect(buttons.map((b) => attr(b, "tabindex"))).toEqual(["0", "-1", "-1", "-1"]);
  });

  it("desabilita todos os botões quando disabled", () => {
    const off = renderToStaticMarkup(
      <IndicatorToggles value={INDICATOR_DEFAULTS} onChange={() => {}} disabled />,
    );
    const offButtons = tagsOf(off, "button");
    expect(offButtons).toHaveLength(4);
    for (const b of offButtons) expect(b).toContain('disabled=""');
  });
});

describe("arquivos de controle sem estado nem efeitos", () => {
  const files = ["../timeframe-bar.tsx", "../pair-selector.tsx", "../indicator-toggles.tsx"];
  it.each(files)("%s não usa useState, useEffect nem useRef", (rel) => {
    const src = readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf8");
    expect(src).not.toMatch(/useState\(|useEffect\(|useRef\(/);
  });
});
