import { afterEach, describe, expect, it, vi } from "vitest";
import { knowledgeSearchPath, memoryListPath, searchKnowledge, listMemory } from "./knowledge-api";

describe("caminhos do contrato (RAG e memória)", () => {
  it("GET /v1/rag/search?q=&k=&tag=", () => {
    expect(knowledgeSearchPath("real", { q: "tarifa ueno", k: 5, tag: "" })).toBe("/v1/rag/search?q=tarifa+ueno&k=5");
    expect(knowledgeSearchPath("real", { q: "horário", k: 10, tag: "chaco" })).toBe("/v1/rag/search?q=hor%C3%A1rio&k=10&tag=chaco");
  });
  it("simulação viaja como data_mode=simulation (D3)", () => {
    expect(knowledgeSearchPath("simulation", { q: "x", k: 5, tag: "" })).toBe("/v1/rag/search?q=x&k=5&data_mode=simulation");
  });
  it("GET /v1/memory?q=&kind=&tag=&limit= sem o sentinela all", () => {
    expect(memoryListPath("real", { q: "", kind: "all", tag: "", limit: 50 })).toBe("/v1/memory?limit=50");
    expect(memoryListPath("real", { q: "ueno", kind: "decision", tag: "fx", limit: 20 })).toBe("/v1/memory?q=ueno&kind=decision&tag=fx&limit=20");
  });
});

describe("modo demonstração nunca toca a rede", () => {
  const original = globalThis.fetch;
  afterEach(() => {
    globalThis.fetch = original;
  });
  it("busca de conhecimento em demo devolve lista vazia sem fetch", async () => {
    const spy = vi.fn(() => Promise.reject(new Error("rede proibida em demo")));
    globalThis.fetch = spy as unknown as typeof fetch;
    await expect(searchKnowledge("demo", { q: "tarifa", k: 5, tag: "" })).resolves.toEqual([]);
    await expect(listMemory("demo", { q: "", kind: "all", tag: "", limit: 20 })).resolves.toEqual([]);
    expect(spy).not.toHaveBeenCalled();
  });
});
