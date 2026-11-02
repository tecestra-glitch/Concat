import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DEFAULT_PREFS, PREFS_KEY, parsePrefs, readPregaoPrefs, resetPregaoPrefsForTests, subscribePregaoPrefs, updatePregaoPrefs, usePregaoPrefs } from "@/lib/pregao/prefs";
import { INDICATOR_DEFAULTS } from "@/lib/pregao/types";

function memoryStorage(initial: Record<string, string> = {}) {
  const data = new Map(Object.entries(initial));
  return {
    getItem: vi.fn((k: string) => data.get(k) ?? null),
    setItem: vi.fn((k: string, v: string) => void data.set(k, v)),
    removeItem: vi.fn((k: string) => void data.delete(k)),
    data,
  };
}

beforeEach(() => resetPregaoPrefsForTests());
afterEach(() => {
  vi.unstubAllGlobals();
  resetPregaoPrefsForTests();
});

describe("parsePrefs (D47: nunca confia no que está gravado)", () => {
  it("sem valor ou JSON inválido → padrão (1 h, só o nº de cotações)", () => {
    expect(DEFAULT_PREFS).toEqual({ tf: "1h", indicators: INDICATOR_DEFAULTS });
    expect(PREFS_KEY).toBe("fx.pregao.prefs");
    expect(parsePrefs(null)).toEqual(DEFAULT_PREFS);
    expect(parsePrefs("{")).toEqual(DEFAULT_PREFS);
    expect(parsePrefs("[]")).toEqual(DEFAULT_PREFS);
  });

  it("aceita intervalo e indicadores válidos", () => {
    const raw = JSON.stringify({ tf: "4h", indicators: { sma: true, ema: false, bollinger: true, volume: false } });
    expect(parsePrefs(raw)).toEqual({ tf: "4h", indicators: { sma: true, ema: false, bollinger: true, volume: false } });
  });

  it("intervalo fora da lista (piso de 60 s → nada abaixo de 15m) volta ao padrão", () => {
    expect(parsePrefs(JSON.stringify({ tf: "1m" })).tf).toBe("1h");
    expect(parsePrefs(JSON.stringify({ tf: 15 })).tf).toBe("1h");
  });

  it("indicador não booleano volta ao padrão daquele indicador, sem chaves extras", () => {
    const p = parsePrefs(JSON.stringify({ tf: "15m", indicators: { sma: "sim", ema: true, extra: true } }));
    expect(p).toEqual({ tf: "15m", indicators: { ...INDICATOR_DEFAULTS, ema: true } });
  });
});

describe("store de preferências", () => {
  it("sem localStorage (servidor, modo privado) devolve o padrão sem lançar", () => {
    expect(readPregaoPrefs()).toEqual(DEFAULT_PREFS);
    expect(() => updatePregaoPrefs({ tf: "1d" })).not.toThrow();
    expect(readPregaoPrefs().tf).toBe("1d");
  });

  it("lê o que está gravado na chave fx.pregao.prefs", () => {
    vi.stubGlobal("localStorage", memoryStorage({ [PREFS_KEY]: JSON.stringify({ tf: "15m" }) }));
    expect(readPregaoPrefs()).toEqual({ tf: "15m", indicators: INDICATOR_DEFAULTS });
  });

  it("updatePregaoPrefs mescla, grava e avisa os inscritos", () => {
    const storage = memoryStorage();
    vi.stubGlobal("localStorage", storage);
    const listener = vi.fn();
    const unsubscribe = subscribePregaoPrefs(listener);
    updatePregaoPrefs({ indicators: { ...INDICATOR_DEFAULTS, sma: true } });
    expect(listener).toHaveBeenCalledTimes(1);
    expect(readPregaoPrefs()).toEqual({ tf: "1h", indicators: { ...INDICATOR_DEFAULTS, sma: true } });
    expect(JSON.parse(storage.data.get(PREFS_KEY) ?? "null")).toEqual({ tf: "1h", indicators: { ...INDICATOR_DEFAULTS, sma: true } });
    unsubscribe();
    updatePregaoPrefs({ tf: "4h" });
    expect(listener).toHaveBeenCalledTimes(1);
  });

  it("setItem que lança (cota cheia) não derruba a tela: o valor vale na memória", () => {
    const storage = memoryStorage();
    storage.setItem.mockImplementation(() => {
      throw new Error("QuotaExceededError");
    });
    vi.stubGlobal("localStorage", storage);
    expect(() => updatePregaoPrefs({ tf: "15m" })).not.toThrow();
    expect(readPregaoPrefs().tf).toBe("15m");
  });

  it("no servidor o hook devolve o padrão (sem divergência de hidratação)", () => {
    vi.stubGlobal("localStorage", memoryStorage({ [PREFS_KEY]: JSON.stringify({ tf: "1d" }) }));
    function Probe() {
      const p = usePregaoPrefs();
      return createElement("span", { "data-tf": p.tf });
    }
    expect(renderToStaticMarkup(createElement(Probe))).toBe('<span data-tf="1h"></span>');
  });
});
