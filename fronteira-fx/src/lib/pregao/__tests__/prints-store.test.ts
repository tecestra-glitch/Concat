import { QueryClient } from "@tanstack/react-query";
import { beforeEach, describe, expect, it } from "vitest";
import type { Quote } from "@/lib/api/types";
import { demoSources } from "@/lib/api/demo-data";
import { quoteToPrint } from "@/lib/pregao/derive";
import { demoQuotesAt } from "@/lib/pregao/demo";
import { midOf } from "@/lib/pregao/candles";
import { PRINTS_MAX, diffQuotes, getSnapshot, pushPrint, resetPrintsForTests, startPrintsFeed } from "@/lib/pregao/prints-store";
import type { Print } from "@/lib/pregao/types";

const NOW = new Date(Date.UTC(2026, 10, 2, 12));
const T0 = Date.UTC(2026, 10, 2, 11, 50);
const iso = (ms: number) => new Date(ms).toISOString();

function houseQuote(sourceId: string, base: Quote["base"]): Quote {
  const q = demoQuotesAt(NOW).find((x) => x.source_id === sourceId && x.base === base);
  if (!q) throw new Error(`cotação demo ausente: ${sourceId} ${base}`);
  return q;
}

const q1: Quote = { ...houseQuote("chaco", "USD"), id: "q1-id", captured_at: iso(T0) };
const q2: Quote = { ...houseQuote("banco-demo-py", "USD"), id: "q2-id", captured_at: iso(T0 + 5 * 60_000) };

/** Modelo de print vindo do próprio conversor; os testes trocam só id e instante. */
function template(): Print {
  const p = quoteToPrint(q1, null, "Cambios Chaco");
  if (!p) throw new Error("print modelo nulo");
  return p;
}

function mkPrint(i: number): Print {
  return { ...template(), id: `p${i}`, captured_at: iso(T0 + i * 1000) };
}

beforeEach(() => {
  resetPrintsForTests();
});

describe("diffQuotes", () => {
  it("cotação nova gera um print sem anterior, com o nome da casa e seen com uma entrada", () => {
    const r = diffQuotes(new Map(), [q1], demoSources);
    expect(r.prints).toHaveLength(1);
    expect(r.prints[0].prev_mid).toBeNull();
    expect(r.prints[0].house).toBe("Cambios Chaco");
    expect(r.seen.size).toBe(1);
  });

  it("mesma cotação não gera print; mudança de compra gera print com a mid anterior", () => {
    const r1 = diffQuotes(new Map(), [q1], demoSources);
    const r2 = diffQuotes(r1.seen, [q1], demoSources);
    expect(r2.prints).toHaveLength(0);

    const later = { ...q1, id: "x2", captured_at: iso(T0 + 60_000), buy: "5910" };
    const r3 = diffQuotes(r1.seen, [later], demoSources);
    expect(r3.prints).toHaveLength(1);
    expect(r3.prints[0].prev_mid).toBe(midOf(q1.buy, q1.sell));
    expect(typeof r3.prints[0].change_pct).toBe("number");
  });

  it("não altera o mapa recebido: devolve uma cópia", () => {
    const seen = new Map<string, Quote>();
    const r = diffQuotes(seen, [q1], demoSources);
    expect(seen.size).toBe(0);
    expect(r.seen).not.toBe(seen);
  });
});

describe("prints store", () => {
  it("pushPrint ignora id repetido", () => {
    const p = mkPrint(1);
    pushPrint(p);
    pushPrint(p);
    expect(getSnapshot()).toHaveLength(1);
  });

  it(`corta em PRINTS_MAX, mantém o mais recente primeiro e devolve a mesma referência sem mudanças`, () => {
    expect(PRINTS_MAX).toBe(200);
    for (let i = 0; i < 205; i++) pushPrint(mkPrint(i));
    const snap = getSnapshot();
    expect(snap).toHaveLength(200);
    expect(snap[0].id).toBe("p204");
    expect(getSnapshot()).toBe(snap);
  });

  it("ordena por captured_at desc mesmo quando chegam fora de ordem", () => {
    pushPrint(mkPrint(5));
    pushPrint(mkPrint(9));
    pushPrint(mkPrint(7));
    expect(getSnapshot().map((p) => p.id)).toEqual(["p9", "p7", "p5"]);
  });
});

describe("startPrintsFeed", () => {
  it("transforma atualizações de quotes em prints e ignora queries de outras chaves", () => {
    const qc = new QueryClient();
    const stop = startPrintsFeed(qc);
    qc.setQueryData(["quotes", "real", {}], [q1]);
    qc.setQueryData(["quotes", "real", {}], [q1, q2]);
    expect(getSnapshot()).toHaveLength(2);
    expect(getSnapshot()[0].id).toBe("q2-id");

    qc.setQueryData(["history", "real", "k"], [{ t: iso(T0), buy: "1", sell: "1", mid: "1" }]);
    expect(getSnapshot()).toHaveLength(2);

    stop();
    qc.setQueryData(["quotes", "real", {}], [q1, q2, { ...q2, id: "z", captured_at: iso(T0 + 9 * 60_000) }]);
    expect(getSnapshot()).toHaveLength(2);
    qc.clear();
  });

  it("usa o nome da fonte quando ela está no cache e o source_id quando não está", () => {
    const qc = new QueryClient();
    const stop = startPrintsFeed(qc);
    qc.setQueryData(["sources", "real"], demoSources);
    qc.setQueryData(["quotes", "real", {}], [q1]);
    expect(getSnapshot()[0].house).toBe("Cambios Chaco");
    stop();
    qc.clear();

    resetPrintsForTests();
    const qc2 = new QueryClient();
    const stop2 = startPrintsFeed(qc2);
    qc2.setQueryData(["quotes", "real", {}], [q1]);
    expect(getSnapshot()[0].house).toBe("chaco");
    stop2();
    qc2.clear();
  });
});
