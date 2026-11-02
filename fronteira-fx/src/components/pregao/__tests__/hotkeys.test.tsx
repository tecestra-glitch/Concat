import { readFileSync } from "node:fs";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { buildPregaoBindings, inDialog, isTextTarget, matchHotkey, type HotkeyEventLike } from "@/lib/pregao/use-hotkeys";
import { ShortcutsList, groupBindings, keyLabel } from "@/components/pregao/shortcuts-help";

/** Alvo simulado: em Node não existe `Element`, então `isTextTarget`/`inDialog` aceitam objetos com `tagName` e `closest`. */
function fakeTarget(o: object): EventTarget {
  return o as unknown as EventTarget;
}

function spies() {
  return { setTimeframe: vi.fn(), cyclePair: vi.fn(), toggleHelp: vi.fn(), escape: vi.fn() };
}

function ev(over: Partial<HotkeyEventLike> = {}): HotkeyEventLike {
  return { key: "2", ctrlKey: false, metaKey: false, altKey: false, target: null, ...over };
}

describe("buildPregaoBindings", () => {
  it("devolve as 8 entradas de §0.14 na ordem e com as chaves esperadas", () => {
    const b = buildPregaoBindings(spies());
    expect(b).toHaveLength(8);
    expect(b.map((x) => x.key)).toEqual(["1", "2", "3", "4", "[", "]", "?", "Escape"]);
  });

  it("usa os textos exatos e chama setTimeframe para as teclas 1 a 4", () => {
    const s = spies();
    const b = buildPregaoBindings(s);
    expect(b[1].description).toBe("Velas de 1 hora");
    expect(b[0].group).toBe("Gráfico");
    b[1].handler();
    expect(s.setTimeframe).toHaveBeenCalledWith("1h");
    b[0].handler();
    expect(s.setTimeframe).toHaveBeenLastCalledWith("15m");
  });

  it("troca o par com cyclePair(-1) em [ e cyclePair(1) em ]", () => {
    const s = spies();
    const b = buildPregaoBindings(s);
    b[4].handler();
    expect(s.cyclePair).toHaveBeenCalledWith(-1);
    b[5].handler();
    expect(s.cyclePair).toHaveBeenLastCalledWith(1);
  });

  it("marca ? e Escape como allowInDialog e liga-os a toggleHelp e escape", () => {
    const s = spies();
    const b = buildPregaoBindings(s);
    expect(b[6].allowInDialog).toBe(true);
    expect(b[7].allowInDialog).toBe(true);
    b[6].handler();
    expect(s.toggleHelp).toHaveBeenCalledTimes(1);
    b[7].handler();
    expect(s.escape).toHaveBeenCalledTimes(1);
  });
});

describe("matchHotkey", () => {
  const b = buildPregaoBindings(spies());

  it("casa a tecla pelo key do evento", () => {
    expect(matchHotkey(ev({ key: "2" }), b)?.key).toBe("2");
  });

  it("ignora combinações com ctrl, meta ou alt", () => {
    expect(matchHotkey(ev({ ctrlKey: true }), b)).toBeNull();
    expect(matchHotkey(ev({ metaKey: true }), b)).toBeNull();
    expect(matchHotkey(ev({ altKey: true }), b)).toBeNull();
  });

  it("ignora teclas sem binding", () => {
    expect(matchHotkey(ev({ key: "x" }), b)).toBeNull();
  });

  it("ignora o atalho quando o alvo é campo de texto", () => {
    const input = fakeTarget({ tagName: "INPUT", closest: () => null });
    expect(matchHotkey(ev({ key: "2", target: input }), b)).toBeNull();
    const textarea = fakeTarget({ tagName: "TEXTAREA", closest: () => null });
    expect(matchHotkey(ev({ key: "]", target: textarea }), b)).toBeNull();
  });

  it("dentro de um diálogo ignora as teclas comuns, mas aceita ? e Escape", () => {
    const inside = fakeTarget({ tagName: "DIV", closest: (s: string) => (s === '[role="dialog"]' ? {} : null) });
    expect(matchHotkey(ev({ key: "2", target: inside }), b)).toBeNull();
    expect(matchHotkey(ev({ key: "Escape", target: inside }), b)?.key).toBe("Escape");
    expect(matchHotkey(ev({ key: "?", target: inside }), b)?.key).toBe("?");
  });
});

describe("isTextTarget e inDialog", () => {
  it("reconhece campos de texto e conteúdo editável", () => {
    expect(isTextTarget(fakeTarget({ tagName: "SELECT", closest: () => null }))).toBe(true);
    expect(isTextTarget(fakeTarget({ tagName: "DIV", isContentEditable: true, closest: () => null }))).toBe(true);
    expect(isTextTarget(fakeTarget({ tagName: "DIV", closest: (s: string) => (s === "[contenteditable='true']" ? {} : null) }))).toBe(true);
    expect(isTextTarget(fakeTarget({ tagName: "BUTTON", closest: () => null }))).toBe(false);
    expect(isTextTarget(null)).toBe(false);
  });

  it("detecta alvo dentro de [role=\"dialog\"]", () => {
    expect(inDialog(fakeTarget({ tagName: "DIV", closest: (s: string) => (s === '[role="dialog"]' ? {} : null) }))).toBe(true);
    expect(inDialog(fakeTarget({ tagName: "DIV", closest: () => null }))).toBe(false);
    expect(inDialog(null)).toBe(false);
  });
});

describe("groupBindings e keyLabel", () => {
  it("agrupa na ordem Gráfico, Par, Ajuda com 4, 2 e 2 itens", () => {
    const g = groupBindings(buildPregaoBindings(spies()));
    expect(g.map((x) => x.group)).toEqual(["Gráfico", "Par", "Ajuda"]);
    expect(g.map((x) => x.items.length)).toEqual([4, 2, 2]);
  });

  it("mostra Escape como Esc e deixa as demais teclas iguais", () => {
    expect(keyLabel("Escape")).toBe("Esc");
    expect(keyLabel("2")).toBe("2");
    expect(keyLabel("[")).toBe("[");
  });
});

describe("ShortcutsList", () => {
  it("renderiza as 8 teclas com os textos exatos dentro do <dl> de teste", () => {
    const b = buildPregaoBindings(spies());
    const html = renderToStaticMarkup(<ShortcutsList bindings={b} />);
    expect(html.match(/<kbd/g)).toHaveLength(8);
    for (const text of ["Velas de 15 minutos", "Velas de 1 hora", "Velas de 4 horas", "Velas de 1 dia", "Par anterior", "Próximo par", "Mostrar esta ajuda", "Fechar", "Esc"]) {
      expect(html).toContain(text);
    }
    expect(html).toContain('data-testid="pregao-shortcuts-list"');
  });
});

describe("use-hotkeys.ts (fonte)", () => {
  const src = readFileSync(new URL("../../../lib/pregao/use-hotkeys.ts", import.meta.url), "utf8");

  it("registra exatamente um listener de teclado", () => {
    expect(src.split("addEventListener(")).toHaveLength(2);
  });

  it("não usa useState nem setState (o estado vive nos handlers do container)", () => {
    expect(src).not.toMatch(/useState\(|setState/);
  });
});
