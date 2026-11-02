import { describe, expect, it } from "vitest";
import { DEFAULT_SERIES_KEY, demoCandles } from "@/lib/pregao/demo";
import { atr, bollinger, buildOverlays, closes, ema, sma, vwapProxy } from "@/lib/pregao/indicators";
import { INDICATOR_DEFAULTS, type Candle } from "@/lib/pregao/types";

function candle(t: string, h: string, l: string, c: string, n = 1): Candle {
  return { t, o: c, h, l, c, n, spread_avg: null, buy_c: null, sell_c: null, data_mode: "demo" };
}

describe("closes", () => {
  it("converte o fechamento de cada vela para número", () => {
    const cs = [candle("2026-11-02T10:00:00Z", "10", "8", "9"), candle("2026-11-02T11:00:00Z", "11", "9", "10.5")];
    expect(closes(cs)).toEqual([9, 10.5]);
  });
});

describe("sma", () => {
  it("média móvel simples com nulos antes da primeira janela completa", () => {
    expect(sma([1, 2, 3, 4, 5], 3)).toEqual([null, null, 2, 3, 4]);
  });

  it("um null na entrada anula as saídas seguintes até completar a janela", () => {
    expect(sma([1, null, 3, 4, 5], 3)).toEqual([null, null, null, null, 4]);
  });

  it("entrada vazia devolve lista vazia", () => {
    expect(sma([], 3)).toEqual([]);
  });

  it("period menor que 1 lança RangeError", () => {
    expect(() => sma([1, 2, 3], 0)).toThrow(RangeError);
    expect(() => sma([1, 2, 3], 0)).toThrow("period deve ser inteiro ≥ 1");
  });
});

describe("ema", () => {
  it("semente é a SMA: série constante fica constante", () => {
    expect(ema([2, 2, 2, 2, 2], 3)).toEqual([null, null, 2, 2, 2]);
  });

  it("period 1 acompanha a própria série", () => {
    expect(ema([1, 2, 3, 4, 5], 1)).toEqual([1, 2, 3, 4, 5]);
  });

  it("aplica a recorrência exponencial a partir da semente", () => {
    const out = ema([1, 2, 3, 4], 2);
    expect(out[0]).toBeNull();
    expect(out[1]).toBeCloseTo(1.5, 10);
    expect(out[2]).toBeCloseTo(2.5, 10);
    expect(out[3]).toBeCloseTo(3.5, 10);
  });

  it("recalcula a semente como SMA depois de um null", () => {
    const out = ema([1, 2, null, 3, 4, 5], 2);
    expect(out[1]).toBeCloseTo(1.5, 10);
    expect(out[2]).toBeNull();
    expect(out[3]).toBeNull();
    expect(out[4]).toBeCloseTo(3.5, 10);
    expect(out[5]).toBeCloseTo(4.5, 10);
  });

  it("period não inteiro lança RangeError", () => {
    expect(() => ema([1], 1.5)).toThrow(RangeError);
  });

  it("entrada vazia devolve lista vazia", () => {
    expect(ema([], 3)).toEqual([]);
  });
});

describe("bollinger", () => {
  it("série constante: bandas iguais à média", () => {
    const { middle, upper, lower } = bollinger([5, 5, 5, 5], 2);
    expect(middle).toEqual([null, 5, 5, 5]);
    expect(upper).toEqual(middle);
    expect(lower).toEqual(middle);
  });

  it("desvio populacional: [1, 3] com period 2 dá média 2 e bandas 4 e 0", () => {
    const { middle, upper, lower } = bollinger([1, 3], 2);
    expect(middle[1]).toBe(2);
    expect(upper[1]).toBe(4);
    expect(lower[1]).toBe(0);
  });

  it("defaults period 20 e k 2 sobre 1..20", () => {
    const values = Array.from({ length: 20 }, (_, i) => i + 1);
    const { middle, upper, lower } = bollinger(values);
    const std = Math.sqrt(33.25);
    expect(middle[18]).toBeNull();
    expect(middle[19]).toBeCloseTo(10.5, 10);
    expect(upper[19]).toBeCloseTo(10.5 + 2 * std, 10);
    expect(lower[19]).toBeCloseTo(10.5 - 2 * std, 10);
  });

  it("um null na entrada anula as bandas até a janela voltar a ficar completa", () => {
    const { middle, upper, lower } = bollinger([1, null, 3, 4, 5], 3);
    expect(middle).toEqual([null, null, null, null, 4]);
    expect(upper.slice(0, 4)).toEqual([null, null, null, null]);
    expect(lower.slice(0, 4)).toEqual([null, null, null, null]);
    const std = Math.sqrt(2 / 3);
    expect(upper[4]).toBeCloseTo(4 + 2 * std, 10);
    expect(lower[4]).toBeCloseTo(4 - 2 * std, 10);
  });

  it("entrada vazia devolve três listas vazias", () => {
    expect(bollinger([], 2)).toEqual({ middle: [], upper: [], lower: [] });
  });
});

describe("atr", () => {
  it("uma vela com period 14 devolve só nulo", () => {
    expect(atr([candle("2026-11-02T10:00:00Z", "10", "8", "9")], 14)).toEqual([null]);
  });

  it("três velas com period 2 e period 1", () => {
    const cs = [
      candle("2026-11-02T10:00:00Z", "10", "8", "9"),
      candle("2026-11-02T11:00:00Z", "11", "9", "10"),
      candle("2026-11-02T12:00:00Z", "12", "10", "11"),
    ];
    expect(atr(cs, 2)).toEqual([null, 2, 2]);
    expect(atr(cs, 1)).toEqual([2, 2, 2]);
  });

  it("usa o fechamento anterior para o range verdadeiro (salto de alta)", () => {
    const cs = [candle("2026-11-02T10:00:00Z", "10", "9", "9"), candle("2026-11-02T11:00:00Z", "12", "11", "11")];
    expect(atr(cs, 1)).toEqual([1, 3]);
  });

  it("suavização de Wilder após a semente", () => {
    const cs = [
      candle("2026-11-02T10:00:00Z", "10", "8", "9"),
      candle("2026-11-02T11:00:00Z", "12", "9", "11"),
      candle("2026-11-02T12:00:00Z", "13", "10", "12"),
      candle("2026-11-02T13:00:00Z", "14", "11", "13"),
    ];
    const out = atr(cs, 2);
    expect(out[0]).toBeNull();
    expect(out[1]).toBeCloseTo(2.5, 10);
    expect(out[2]).toBeCloseTo(2.75, 10);
    expect(out[3]).toBeCloseTo(2.875, 10);
  });

  it("period menor que 1 lança RangeError", () => {
    expect(() => atr([candle("2026-11-02T10:00:00Z", "10", "8", "9")], 0)).toThrow(RangeError);
  });

  it("entrada vazia devolve lista vazia", () => {
    expect(atr([], 14)).toEqual([]);
  });
});

describe("vwapProxy", () => {
  it("média ponderada por n, reiniciando a cada dia UTC", () => {
    const cs = [
      candle("2026-11-01T10:00:00Z", "10", "10", "10", 1),
      candle("2026-11-01T11:00:00Z", "20", "20", "20", 3),
      candle("2026-11-02T00:00:00Z", "30", "30", "30", 1),
    ];
    expect(vwapProxy(cs)).toEqual([10, 17.5, 30]);
  });

  it("vela com n = 0 devolve null sem alterar o acumulado", () => {
    const cs = [
      candle("2026-11-01T10:00:00Z", "10", "10", "10", 1),
      candle("2026-11-01T11:00:00Z", "20", "20", "20", 0),
      candle("2026-11-01T12:00:00Z", "20", "20", "20", 3),
    ];
    expect(vwapProxy(cs)).toEqual([10, null, 17.5]);
  });

  it("entrada vazia devolve lista vazia", () => {
    expect(vwapProxy([])).toEqual([]);
  });
});

describe("buildOverlays", () => {
  const cs = demoCandles(DEFAULT_SERIES_KEY, "1h", new Date(Date.UTC(2026, 10, 2, 12)), 30);

  it("sem indicadores ligados não devolve chaves", () => {
    expect(Object.keys(buildOverlays(cs, INDICATOR_DEFAULTS))).toHaveLength(0);
  });

  it("SMA e Bollinger ligados devolvem exatamente as chaves sma, bbUpper e bbLower", () => {
    const overlays = buildOverlays(cs, { ...INDICATOR_DEFAULTS, sma: true, bollinger: true });
    expect(Object.keys(overlays)).toEqual(["sma", "bbUpper", "bbLower"]);
    for (const key of ["sma", "bbUpper", "bbLower"] as const) {
      expect(overlays[key]).toHaveLength(cs.length);
    }
  });

  it("EMA ligada devolve só a chave ema", () => {
    const overlays = buildOverlays(cs, { ...INDICATOR_DEFAULTS, ema: true });
    expect(Object.keys(overlays)).toEqual(["ema"]);
    expect(overlays.ema).toHaveLength(cs.length);
  });
});

describe("preservação do comprimento", () => {
  const cs = demoCandles(DEFAULT_SERIES_KEY, "1h", new Date(Date.UTC(2026, 10, 2, 12)), 30);
  const cl = closes(cs);

  it("todas as séries têm o mesmo comprimento da entrada", () => {
    expect(cs).toHaveLength(30);
    expect(sma(cl, 5)).toHaveLength(30);
    expect(ema(cl, 9)).toHaveLength(30);
    const b = bollinger(cl, 20, 2);
    expect(b.middle).toHaveLength(30);
    expect(b.upper).toHaveLength(30);
    expect(b.lower).toHaveLength(30);
    expect(atr(cs, 14)).toHaveLength(30);
    expect(vwapProxy(cs)).toHaveLength(30);
  });
});
