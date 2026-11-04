import { describe, expect, it } from "vitest";
import type { MarketVolatility } from "@/lib/api/market";
import { changeTone, formatChangePct, formatReference, formatVolPct, safeExternalHref, sourceLabel, volatilityView } from "./economia-helpers";

const base: MarketVolatility = {
  instrument: "USDT/BRL",
  status: "ok",
  as_of: "2026-11-04T12:00:00+00:00",
  last_close: "5.5179",
  last_move_pct: "0.12",
  ewma_pct_5m: "0.08",
  parkinson_1d_pct: "0.41",
  parkinson_20d_pct: "0.37",
  ratio_1d_20d: "1.11",
  atr_14_5m: "0.0061",
  regime: "normal",
  alert: false,
  reasons: [],
  data_mode: "real",
};

describe("volatilityView (selo normal / alta / muito alta)", () => {
  it("mapeia cada regime para o selo e a variante certos", () => {
    expect(volatilityView({ ...base, regime: "normal" })).toMatchObject({ label: "normal", variant: "default" });
    expect(volatilityView({ ...base, regime: "alta" })).toMatchObject({ label: "alta", variant: "warn" });
    expect(volatilityView({ ...base, regime: "muito_alta", alert: true })).toMatchObject({ label: "muito alta", variant: "loss" });
  });

  it("sem dados suficientes ou com dados antigos não mostra regime nenhum", () => {
    expect(volatilityView({ ...base, status: "insufficient_data", regime: null })).toMatchObject({ label: "dados insuficientes", variant: "outline" });
    expect(volatilityView({ ...base, status: "stale_input", regime: null })).toMatchObject({ label: "dados antigos", variant: "outline" });
  });
});

describe("formatReference (exibição pt-BR, sem alterar o valor)", () => {
  it("mantém a precisão da referência e usa separadores pt-BR", () => {
    expect(formatReference("5.5179")).toBe("5,5179");
    expect(formatReference("76006.95")).toBe("76.006,95");
    expect(formatReference("5958")).toBe("5.958");
    expect(formatReference("13.75")).toBe("13,75");
  });

  it("valores abaixo de 1 ganham mais casas e nulos viram traço", () => {
    expect(formatReference("0.0061")).toBe("0,0061");
    expect(formatReference(null)).toBe("—");
    expect(formatReference("abc")).toBe("—");
  });
});

describe("variação e volatilidade", () => {
  it("variação com sinal explícito e tom", () => {
    expect(formatChangePct("0.88")).toBe("+0,88 %");
    expect(formatChangePct("-1.18")).toMatch(/^-1,18 %$/);
    expect(formatChangePct(null)).toBe("—");
    expect(changeTone("0.88")).toBe("gain");
    expect(changeTone("-1.18")).toBe("loss");
    expect(changeTone(null)).toBe("muted");
  });

  it("percentual de volatilidade já em % com duas casas", () => {
    expect(formatVolPct("1.6234")).toBe("1,62 %");
    expect(formatVolPct(undefined)).toBe("—");
  });
});

describe("links e fontes (texto de feed é dado não confiável)", () => {
  it("só http(s) vira link; outros esquemas viram texto", () => {
    expect(safeExternalHref("https://www.infomoney.com.br/x")).toBe("https://www.infomoney.com.br/x");
    expect(safeExternalHref("javascript:alert(1)")).toBeNull();
    expect(safeExternalHref("data:text/html,<b>x</b>")).toBeNull();
    expect(safeExternalHref("não é url")).toBeNull();
  });

  it("rótulos das fontes conhecidas e desconhecidas", () => {
    expect(sourceLabel("agencia-brasil")).toBe("Agência Brasil");
    expect(sourceLabel("outra")).toBe("outra");
  });
});
