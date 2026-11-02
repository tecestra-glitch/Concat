import { describe, expect, it } from "vitest";
import type { Change } from "@/lib/api/watch";
import { changeCounts } from "./stat-helpers";

const NOW = Date.parse("2026-11-02T12:00:00Z");
function ch(hoursAgo: number): Change {
  return { id: `c${hoursAgo}`, source_id: "chaco", ts: new Date(NOW - hoursAgo * 3_600_000).toISOString(), kind: "quote_change", summary: "", before: {}, after: {}, evidence_id: null, data_mode: "demo" };
}

describe("changeCounts (stat-row conta 24 h de verdade)", () => {
  it("separa última hora e últimas 24 h; o que passou de 24 h fica fora", () => {
    const counts = changeCounts([ch(0.5), ch(3), ch(23), ch(25), ch(48)], NOW);
    expect(counts.lastHour).toBe(1);
    expect(counts.last24h).toBe(3);
  });
  it("relógio zero (antes da hidratação) devolve nulos", () => {
    expect(changeCounts([ch(1)], 0)).toEqual({ lastHour: null, last24h: null });
  });
});
