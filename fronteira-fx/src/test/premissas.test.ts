import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { PREMISSAS_RAILS, PREMISSAS_TRANSPORT, premissaStatus } from "@/lib/api/premissas";

// A cópia do frontend espelha os dados versionados do backend: se um lado mudar, este teste acusa.
const read = (name: string) => JSON.parse(readFileSync(new URL(`../../backend/src/fronteira_fx/data/${name}`, import.meta.url), "utf8"));

describe("premissas do cruzamento (espelho dos dados versionados do backend)", () => {
  it("rotas entre cidades batem com transport.json", () => {
    expect(PREMISSAS_TRANSPORT.map((r) => r.id)).toEqual(read("transport.json").map((r: { id: string }) => r.id));
    for (const raw of read("transport.json") as Array<{ id: string; minutes: number; cost: unknown; verified: boolean; border: boolean }>) {
      const mine = PREMISSAS_TRANSPORT.find((r) => r.id === raw.id)!;
      expect(mine.minutes).toBe(raw.minutes);
      expect(mine.verified).toBe(raw.verified);
      expect(mine.border).toBe(raw.border);
      expect(mine.cost).toBeNull();
    }
  });
  it("trilhos batem com rails.json", () => {
    expect(PREMISSAS_RAILS.map((r) => r.id)).toEqual(read("rails.json").map((r: { id: string }) => r.id));
  });
  it("sem fonte e sem verificação aparece como não verificado, nunca como confirmado", () => {
    expect(premissaStatus({ verified: false, source_url: null, checked_at: null })).toEqual({ verified: false, label: "não verificado", source: "fonte não informada" });
    expect(premissaStatus({ verified: true, source_url: "https://x.test", checked_at: "2026-10-30" })).toEqual({ verified: true, label: "verificado", source: "https://x.test" });
  });
});
