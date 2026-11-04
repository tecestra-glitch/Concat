import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { formatPercent } from "@/lib/format";
import type { SessionStats } from "@/lib/pregao/types";
import { STALE_AFTER_MS, StatsStrip, rangePosition, statsCells } from "@/components/pregao/stats-strip";

/** Exemplo canônico de §0.4 com `last_at` e `houses` da spec de F10 (§18.3). */
const stats: SessionStats = {
  key: "chaco:CDE:USD/PYG:cash",
  day_start: "2026-11-02T00:00:00-03:00",
  open: "7335",
  high: "7340",
  low: "7318",
  last: "7340",
  last_at: "2026-11-02T12:16:00Z",
  change_abs: "5",
  change_pct: "0.0681663",
  n_quotes: 4,
  spread_avg: "30",
  houses: 5,
  data_mode: "real",
};

const now = Date.UTC(2026, 10, 2, 12, 20);

const count = (html: string, needle: string): number => html.split(needle).length - 1;

describe("statsCells", () => {
  it("devolve as 8 células na ordem da spec com os valores da sessão", () => {
    const cells = statsCells(stats, "PYG", now);
    expect(cells.map((c) => c.label)).toEqual([
      "Abertura",
      "Máxima",
      "Mínima",
      "Último",
      "Variação",
      "Faixa do dia",
      "Cotações",
      "Spread médio",
    ]);
    expect(cells[0].value).toBe("7.335");
    expect(cells[4].deltaAbs).toBe(5);
    expect(cells[4].deltaPct).toBeCloseTo(0.0681663, 5);
    expect(cells[6].value).toBe("4");
    expect(cells[6].sub).toBe("5 casas");
    expect(cells[7].value).toBe("30");
    expect(cells[7].sub).toMatch(/^0,41/);
  });

  it("usa singular quando há uma única casa", () => {
    expect(statsCells({ ...stats, houses: 1 }, "PYG", now)[6].sub).toBe("1 casa");
  });

  it("sem sessão devolve 8 células com valores em —", () => {
    const cells = statsCells(null, "PYG", now);
    expect(cells).toHaveLength(8);
    expect(cells.filter((c) => c.id !== "change").every((c) => c.value === "—")).toBe(true);
    expect(cells[4].deltaAbs ?? null).toBeNull();
    expect(cells[4].deltaPct ?? null).toBeNull();
  });

  it("spread nulo mostra — sem subtítulo", () => {
    const spread = statsCells({ ...stats, spread_avg: null }, "PYG", now)[7];
    expect(spread.value).toBe("—");
    expect(spread.sub).toBeUndefined();
  });

  it("aviso de atualização antiga só depois de 15 min", () => {
    const lastAt = Date.parse("2026-11-02T12:16:00Z");
    expect(STALE_AFTER_MS).toBe(15 * 60_000);
    expect(statsCells(stats, "PYG", now)[3].warn).toBeUndefined();
    expect(statsCells(stats, "PYG", lastAt + 2 * 60_000)[3].warn).toBeUndefined();
    expect(statsCells(stats, "PYG", lastAt + STALE_AFTER_MS)[3].warn).toBeUndefined();
    const later = Date.UTC(2026, 10, 2, 12, 40);
    expect(statsCells(stats, "PYG", later)[3].warn?.startsWith("última atualização há ")).toBe(true);
    expect(statsCells(stats, "PYG", 0)[3].warn).toBeUndefined();
  });
});

describe("rangePosition", () => {
  it("posição de 0 a 100 da última cotação na faixa mín–máx", () => {
    expect(rangePosition("7318", "7340", "7340")).toBe(100);
    expect(rangePosition("7318", "7340", "7329")).toBe(50);
    expect(rangePosition("7318", "7340", "7318")).toBe(0);
  });

  it("nunca sai de 0 a 100", () => {
    expect(rangePosition("7318", "7340", "7400")).toBe(100);
    expect(rangePosition("7318", "7340", "7300")).toBe(0);
  });

  it("null quando falta valor ou a faixa é nula", () => {
    expect(rangePosition("1", "1", "1")).toBeNull();
    expect(rangePosition(null, "1", "1")).toBeNull();
    expect(rangePosition("1", null, "1")).toBeNull();
    expect(rangePosition("1", "2", null)).toBeNull();
  });
});

describe("StatsStrip (SSR)", () => {
  it("raiz com data-state ready, data-day-start e 8 tiles", () => {
    const html = renderToStaticMarkup(<StatsStrip stats={stats} quote="PYG" now={now} />);
    expect(html).toContain('data-testid="pregao-stats"');
    expect(html).toContain('data-state="ready"');
    expect(html).toContain('data-day-start="2026-11-02T00:00:00-03:00"');
    expect(count(html, "<dt")).toBe(8);
    expect(html).toContain("corte diário 00:00 Assunção");
  });

  it("faixa do dia é role=img com aria-label de mínima, máxima e último", () => {
    const html = renderToStaticMarkup(<StatsStrip stats={stats} quote="PYG" now={now} />);
    expect(html).toContain('role="img"');
    expect(html).toContain("mínima 7.318");
    expect(html).toContain("último 7.340");
  });

  it("variação de alta: dois deltas com seta, sinal e data-direction up", () => {
    const html = renderToStaticMarkup(<StatsStrip stats={stats} quote="PYG" now={now} />);
    expect(count(html, 'data-direction="up"')).toBe(2);
    expect(html).toContain("+5");
    expect(html).toContain(formatPercent(0.0681663 / 100, { sign: true }));
    expect(html).toContain(" subiu");
  });

  it("variação de baixa usa text-loss e data-direction down", () => {
    const html = renderToStaticMarkup(
      <StatsStrip stats={{ ...stats, change_abs: "-5", change_pct: "-0.0681663" }} quote="PYG" now={now} />,
    );
    expect(count(html, 'data-direction="down"')).toBe(2);
    expect(count(html, "text-loss")).toBe(2);
    expect(html).toContain(" caiu");
  });

  it("cor só nos deltas: text-gain e text-loss só aparecem nos dois pregao-delta", () => {
    const html = renderToStaticMarkup(<StatsStrip stats={stats} quote="PYG" now={now} />);
    expect(count(html, "text-gain")).toBe(2);
    expect(count(html, "text-loss")).toBe(0);
  });

  it("aviso de última atualização antiga aparece no tile Último", () => {
    const later = Date.UTC(2026, 10, 2, 12, 40);
    const html = renderToStaticMarkup(<StatsStrip stats={stats} quote="PYG" now={later} />);
    expect(html).toContain("última atualização há 24 min");
  });

  it("stats null: estado ready com todos os valores em —", () => {
    const html = renderToStaticMarkup(<StatsStrip stats={null} quote="PYG" now={now} />);
    expect(html).toContain('data-state="ready"');
    expect(count(html, "—")).toBeGreaterThanOrEqual(8);
  });

  it("sessão sem cotações: estado empty com mensagem", () => {
    const html = renderToStaticMarkup(<StatsStrip stats={{ ...stats, n_quotes: 0 }} quote="PYG" now={now} />);
    expect(html).toContain('data-state="empty"');
    expect(html).toContain("Sessão sem cotações até agora.");
  });

  it("loading: 8 skeletons, aria-busy e texto sr-only", () => {
    const html = renderToStaticMarkup(<StatsStrip stats={null} quote="PYG" now={now} loading />);
    expect(html).toContain('data-state="loading"');
    expect(html).toContain('aria-busy="true"');
    // Esqueleto com brilho do fx (globals.css), no lugar do animate-pulse (spec §4, item 11).
    expect(count(html, "fx-skeleton")).toBe(8);
    expect(html).toContain("Carregando…");
  });

  it("error: role alert com mensagem e botão só quando há onRetry", () => {
    const err = new Error("HTTP 502");
    const semRetry = renderToStaticMarkup(<StatsStrip stats={stats} quote="PYG" now={now} error={err} />);
    expect(semRetry).toContain('data-state="error"');
    expect(semRetry).toContain('role="alert"');
    expect(semRetry).toContain("Não foi possível carregar as estatísticas da sessão.");
    expect(semRetry).toContain("HTTP 502");
    expect(semRetry).not.toContain("Tentar de novo");

    const comRetry = renderToStaticMarkup(
      <StatsStrip stats={stats} quote="PYG" now={now} error={err} onRetry={() => undefined} />,
    );
    expect(comRetry).toContain("Tentar de novo");
  });

  it("loading tem precedência sobre error", () => {
    const html = renderToStaticMarkup(
      <StatsStrip stats={stats} quote="PYG" now={now} loading error={new Error("x")} />,
    );
    expect(html).toContain('data-state="loading"');
  });
});
