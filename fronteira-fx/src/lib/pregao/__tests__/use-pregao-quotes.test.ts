import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { demoQuotesAt } from "@/lib/pregao/demo";
import { pregaoQuotesFor } from "@/lib/pregao/use-pregao-quotes";
import type { Quote } from "@/lib/api/types";

const NOW = Date.UTC(2026, 10, 2, 12, 0);
const fetched = [{ id: "q-1", data_mode: "real" }] as unknown as Quote[];

describe("pregaoQuotesFor (cotações da tela por modo)", () => {
  it("demo sem relógio (servidor, hidratação): nenhuma cotação", () => {
    expect(pregaoQuotesFor("demo", fetched, 0)).toEqual([]);
  });

  it("demo: cotações recarimbadas com o relógio da tela, todas data_mode demo", () => {
    const q = pregaoQuotesFor("demo", fetched, NOW);
    expect(q).toEqual(demoQuotesAt(new Date(NOW)));
    expect(q.length).toBeGreaterThan(0);
    expect(q.every((x) => x.data_mode === "demo")).toBe(true);
    expect(q.every((x) => Date.parse(x.captured_at) < NOW && Date.parse(x.captured_at) >= NOW - 10 * 60_000)).toBe(true);
  });

  it("real e simulação: as cotações da API, sem mistura com demo", () => {
    expect(pregaoQuotesFor("real", fetched, NOW)).toBe(fetched);
    expect(pregaoQuotesFor("simulation", fetched, NOW)).toBe(fetched);
  });

  it("o hook chama useQuotes e useSources incondicionalmente", () => {
    const src = readFileSync(new URL("../use-pregao-quotes.ts", import.meta.url).pathname, "utf8");
    expect(src.startsWith('"use client";')).toBe(true);
    expect(src).toMatch(/const quotesQ = useQuotes\(\);/);
    expect(src).toMatch(/const sourcesQ = useSources\(\);/);
    expect(src).not.toMatch(/Date\.now\(|new Date\(\)/);
  });
});
