import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { LineStyle } from "lightweight-charts";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { CandleChart } from "@/components/pregao/candle-chart";
import {
  FALLBACK_TOKENS,
  TOKEN_VARS,
  buildCandleOptions,
  buildChartOptions,
  buildLineOptions,
  buildVolumeOptions,
  chartAriaLabel,
  formatTick,
  overlayLineData,
  toCandlestickData,
  toLineData,
  toVolumeData,
  tokensFromGetter,
} from "@/components/pregao/candle-chart-options";
import { INDICATOR_DEFAULTS, type Candle, type CandleSeries } from "@/lib/pregao/types";

// Velas do exemplo canônico de §0.4 (chaco:CDE:USD/PYG:cash, real, 2026-11-02 UTC, intervalo 15 min).
const C1: Candle = { t: "2026-11-02T12:00:00.000Z", o: "7335", h: "7337", l: "7318", c: "7318", n: 3, spread_avg: "30", buy_c: "7318", sell_c: "7352", data_mode: "real" };
const C2: Candle = { t: "2026-11-02T12:15:00.000Z", o: "7340", h: "7340", l: "7340", c: "7340", n: 1, spread_avg: "30", buy_c: "7325", sell_c: "7355", data_mode: "real" };
const T1 = Date.UTC(2026, 10, 2, 12) / 1000;
const T2 = T1 + 900;
const SERIES: CandleSeries = { key: "chaco:CDE:USD/PYG:cash", tf: "15m", candles: [C1, C2], data_mode: "real" };

describe("toCandlestickData e toVolumeData", () => {
  it("converte a vela de 12:00Z em tempo UTC inteiro e preços numéricos", () => {
    expect(toCandlestickData([C1])[0]).toEqual({ time: T1, open: 7335, high: 7337, low: 7318, close: 7318 });
  });

  it("usa o número de cotações como valor do histograma", () => {
    expect(toVolumeData([C1])[0].value).toBe(3);
  });
});

describe("toLineData", () => {
  it("emite espaço em branco onde o indicador ainda não existe", () => {
    expect(toLineData([C1, C2], [null, 5])).toEqual([{ time: T1 }, { time: T2, value: 5 }]);
  });

  it("lança RangeError quando a série não tem a mesma extensão das velas", () => {
    expect(() => toLineData([C1, C2], [1])).toThrow(RangeError);
  });
});

describe("overlayLineData", () => {
  it("sem valores, ou com extensão diferente das velas, não desenha a linha (sem derrubar o gráfico)", () => {
    expect(overlayLineData([C1, C2], undefined)).toEqual([]);
    expect(overlayLineData([C1, C2], [1])).toEqual([]);
  });

  it("com valores alinhados delega para toLineData", () => {
    expect(overlayLineData([C1, C2], [null, 5])).toEqual(toLineData([C1, C2], [null, 5]));
  });
});

describe("buildCandleOptions", () => {
  it("usa passo 1 para PYG e 0,0001 para BRL", () => {
    expect(buildCandleOptions(FALLBACK_TOKENS, "PYG").priceFormat?.minMove).toBe(1);
    expect(buildCandleOptions(FALLBACK_TOKENS, "BRL").priceFormat?.minMove).toBe(0.0001);
  });

  it("deixa a alta com corpo vazado e a baixa cheia, nas cores dos tokens", () => {
    const o = buildCandleOptions(FALLBACK_TOKENS, "PYG");
    expect(o.upColor).toBe("rgba(0,0,0,0)");
    expect(o.downColor).toBe(FALLBACK_TOKENS.loss);
    expect(o.borderUpColor).toBe(FALLBACK_TOKENS.gain);
  });
});

describe("buildChartOptions", () => {
  it("mostra a hora só nos intervalos intradiários", () => {
    expect(buildChartOptions(FALLBACK_TOKENS, { tf: "1d", quote: "PYG" }).timeScale?.timeVisible).toBe(false);
    expect(buildChartOptions(FALLBACK_TOKENS, { tf: "15m", quote: "PYG" }).timeScale?.timeVisible).toBe(true);
  });

  it("ajusta ao contêiner e mantém a atribuição do lightweight-charts", () => {
    const o = buildChartOptions(FALLBACK_TOKENS, { tf: "1h", quote: "PYG" });
    expect(o.autoSize).toBe(true);
    expect(o.layout?.attributionLogo).toBe(true);
  });
});

describe("buildLineOptions e buildVolumeOptions", () => {
  it("deixa SMA e EMA ocultas por padrão e a banda tracejada", () => {
    expect(buildLineOptions(FALLBACK_TOKENS, "sma").visible).toBe(false);
    expect(buildLineOptions(FALLBACK_TOKENS, "ema").visible).toBe(false);
    expect(buildLineOptions(FALLBACK_TOKENS, "band").lineStyle).toBe(LineStyle.Dashed);
  });

  it("põe o histograma na escala 'volume' sem linha de preço", () => {
    const o = buildVolumeOptions(FALLBACK_TOKENS);
    expect(o.priceScaleId).toBe("volume");
    expect(o.priceFormat).toEqual({ type: "volume" });
    expect(o.priceLineVisible).toBe(false);
  });
});

describe("tokensFromGetter", () => {
  it("usa o fallback quando a variável CSS vem vazia", () => {
    expect(tokensFromGetter(() => "")).toEqual(FALLBACK_TOKENS);
  });

  it("lê cada token da sua variável e cai no fallback por token", () => {
    const t = tokensFromGetter((v) => (v === "--gain" ? "#047857" : ""));
    expect(t.gain).toBe("#047857");
    expect(t.loss).toBe(FALLBACK_TOKENS.loss);
  });

  it("mapeia os tokens para as variáveis de §0.13", () => {
    expect(TOKEN_VARS.surface).toBe("--surface");
    expect(TOKEN_VARS.volume).toBe("--chart-volume");
    expect(TOKEN_VARS.fontMono).toBe("--font-mono");
  });
});

describe("chartAriaLabel", () => {
  it("descreve par, casa, intervalo, contagem e último valor", () => {
    expect(
      chartAriaLabel({ pair: "USD/PYG", house: "Cambios Chaco", tf: "1h", count: 180, last: "7312", quote: "PYG" }),
    ).toBe("Gráfico de velas USD/PYG, Cambios Chaco, intervalo 1 hora, 180 velas, último 7.312");
  });

  it("sem velas diz que não há dados", () => {
    expect(chartAriaLabel({ pair: "USD/PYG", house: "", tf: "1h", count: 0, last: null, quote: "PYG" })).toBe(
      "Gráfico de velas sem dados",
    );
  });

  it("omite a vírgula quando não há nome da casa", () => {
    expect(chartAriaLabel({ pair: "USD/PYG", house: "", tf: "1h", count: 2, last: "7318", quote: "PYG" })).toBe(
      "Gráfico de velas USD/PYG, intervalo 1 hora, 2 velas, último 7.318",
    );
  });
});

describe("formatTick", () => {
  const ASU_1504 = Date.UTC(2026, 10, 2, 15, 4) / 1000;

  it("formata a hora no fuso de Assunção sem deslocar o instante", () => {
    expect(formatTick(ASU_1504, "time")).toBe("12:04");
  });

  it("formata dia/mês e ano em pt-BR", () => {
    expect(formatTick(ASU_1504, "day")).toBe("02/11");
    expect(formatTick(ASU_1504, "year")).toBe("2026");
  });
});

describe("fonte de candle-chart", () => {
  const source = readFileSync(fileURLToPath(new URL("../candle-chart.tsx", import.meta.url)), "utf8");
  const optionsSource = readFileSync(fileURLToPath(new URL("../candle-chart-options.ts", import.meta.url)), "utf8");

  it("chama createChart uma única vez, para não recriar o gráfico a cada atualização", () => {
    expect(source.split("createChart(").length - 1).toBe(1);
  });

  it("não tem cor em hexadecimal nos dois arquivos (cores vêm dos tokens)", () => {
    expect(source).not.toMatch(/#[0-9a-fA-F]{3,6}\b/);
    expect(optionsSource).not.toMatch(/#[0-9a-fA-F]{3,6}\b/);
  });

  it("marca a raiz com data-testid e a faixa de demonstração", () => {
    expect(source).toContain('data-testid="pregao-chart"');
    expect(source).toContain("DEMONSTRAÇÃO");
  });

  it("figure com figcaption, sem role=img: o link de atribuição da biblioteca e o «Tentar de novo» ficam dentro (axe nested-interactive)", () => {
    expect(source).toMatch(/<figure\b/);
    expect(source).toMatch(/<figcaption className="sr-only">/);
    expect(source).not.toMatch(/role="img"/);
  });
});

describe("CandleChart — três estados (§0.12)", () => {
  const BASE = { timeframe: "15m" as const, quote: "PYG" as const, indicators: INDICATOR_DEFAULTS, house: "Cambios Chaco" };

  it("carregando: data-state loading, aria-busy e texto para leitor de tela", () => {
    const html = renderToStaticMarkup(<CandleChart {...BASE} series={SERIES} loading />);
    expect(html).toContain('data-state="loading"');
    expect(html).toContain('aria-busy="true"');
    expect(html).toContain("Carregando…");
  });

  it("erro: role alert com mensagem, e o botão só existe quando há onRetry", () => {
    const err = new Error("500 Internal Server Error em /v1/candles");
    const withRetry = renderToStaticMarkup(<CandleChart {...BASE} series={null} error={err} onRetry={() => {}} />);
    expect(withRetry).toContain('data-state="error"');
    expect(withRetry).toContain('role="alert"');
    expect(withRetry).toContain("Não foi possível carregar o gráfico.");
    expect(withRetry).toContain("Tentar de novo");
    const noRetry = renderToStaticMarkup(<CandleChart {...BASE} series={null} error={err} />);
    expect(noRetry).not.toContain("Tentar de novo");
  });

  it("carregando vence erro na precedência", () => {
    const html = renderToStaticMarkup(<CandleChart {...BASE} series={SERIES} loading error={new Error("x")} />);
    expect(html).toContain('data-state="loading"');
  });

  it("vazio: sem velas mostra a mensagem e marca data-state empty", () => {
    const html = renderToStaticMarkup(<CandleChart {...BASE} series={{ ...SERIES, candles: [] }} />);
    expect(html).toContain('data-state="empty"');
    expect(html).toContain("Sem velas para este período.");
  });

  it("pronto: data-state ready, contêiner visível, legenda e rótulo com o último valor", () => {
    const html = renderToStaticMarkup(<CandleChart {...BASE} series={SERIES} />);
    expect(html).toContain('data-state="ready"');
    expect(html).toContain('data-key="chaco:CDE:USD/PYG:cash"');
    expect(html).toContain("intervalo 15 min, 2 velas, último 7.340");
    expect(html).toContain('aria-label="Séries do gráfico"');
    expect(html).toContain("Nº de cotações");
    expect(html).not.toContain('hidden=""');
  });

  it("legenda acrescenta a SMA quando o indicador está ligado", () => {
    const html = renderToStaticMarkup(<CandleChart {...BASE} series={SERIES} indicators={{ ...INDICATOR_DEFAULTS, sma: true }} />);
    expect(html).toContain("SMA 20");
    expect(html).not.toContain("EMA 9");
  });

  it("demo marca data-mode na raiz", () => {
    const html = renderToStaticMarkup(<CandleChart {...BASE} series={SERIES} demo />);
    expect(html).toContain('data-mode="demo"');
  });
});
