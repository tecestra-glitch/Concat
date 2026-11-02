import { describe, expect, it } from "vitest";
import { diffPct, impliedBrlPyg, isStale, legOf, midOfLeg, type Leg } from "@/lib/pregao/cross";
import type { BookLevel } from "@/lib/pregao/types";

const now = new Date(Date.UTC(2026, 10, 2, 12));
const at = "2026-11-02T11:50:00Z";

function leg(buy: string | null, sell: string | null, captured_at = at): Leg {
  return { buy, sell, captured_at };
}

describe("impliedBrlPyg", () => {
  it("calcula BRL/PYG implícito pelas pernas USD da mesma casa", () => {
    const r = impliedBrlPyg(leg("5905", "5975"), leg("5.40", "5.46"), now);
    expect(Math.abs(Number(r.buy) - 1081.5018)).toBeLessThan(1e-3);
    expect(Math.abs(Number(r.sell) - 1106.4815)).toBeLessThan(1e-3);
    expect(r.incomplete).toBe(false);
    expect(r.stale).toBe(false);
  });

  it("sem Venda em USD/BRL a Compra implícita fica nula e a casa fica incompleta", () => {
    const r = impliedBrlPyg(leg("5905", "5975"), leg("5.40", null), now);
    expect(r.buy).toBeNull();
    expect(r.sell).not.toBeNull();
    expect(r.incomplete).toBe(true);
  });

  it("sem Compra em USD/BRL a Venda implícita fica nula", () => {
    const r = impliedBrlPyg(leg("5905", "5975"), leg(null, "5.46"), now);
    expect(r.sell).toBeNull();
    expect(r.incomplete).toBe(true);
  });

  it("perna com captured_at de 25 h é antiga e os valores continuam calculados", () => {
    const old = "2026-11-01T11:00:00Z";
    const r = impliedBrlPyg(leg("5905", "5975", old), leg("5.40", "5.46", at), now);
    expect(r.stale).toBe(true);
    expect(r.buy).not.toBeNull();
    expect(r.sell).not.toBeNull();
    expect(isStale({ buy: "1", sell: "1", captured_at: "x" }, now)).toBe(true);
  });
});

describe("diffPct", () => {
  it("compara direto e implícito em percentual", () => {
    const r = impliedBrlPyg(leg("5905", "5975"), leg("5.40", "5.46"), now);
    expect(Math.abs((diffPct("1092", r.buy) ?? NaN) - 0.9707)).toBeLessThan(1e-3);
    expect(Math.abs((diffPct("1112", r.sell) ?? NaN) - 0.4987)).toBeLessThan(1e-3);
    expect(diffPct(null, "1")).toBeNull();
    expect(diffPct("1", "0")).toBeNull();
  });
});

describe("legOf e midOfLeg", () => {
  it("legOf(undefined) é nulo e legOf copia buy, sell e captured_at", () => {
    expect(legOf(undefined)).toBeNull();
    const level: BookLevel = {
      key: "chaco:CDE:USD/PYG:cash",
      pair: "USD/PYG",
      source_id: "chaco",
      house: "Cambios Chaco",
      city: "CDE",
      channel: "physical",
      kind: "indicative",
      buy: "10",
      sell: "12",
      spread_pct: null,
      agio_buy_pct: null,
      agio_sell_pct: null,
      status: "open",
      incomplete: false,
      captured_at: at,
      data_mode: "real",
    };
    expect(legOf(level)).toEqual({ buy: "10", sell: "12", captured_at: at });
    expect(midOfLeg({ buy: "10", sell: "12", captured_at: at })).toBe(11);
  });
});
