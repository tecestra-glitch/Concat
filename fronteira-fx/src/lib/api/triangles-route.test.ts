import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "./client";

const fetchMock = vi.fn<typeof fetch>();
const modeParam = (call: number) => new URL(String(fetchMock.mock.calls[call]?.[0]), "http://local").searchParams.get("mode");

beforeEach(() => {
  fetchMock.mockReset();
  fetchMock.mockImplementation(async () => new Response("[]", { status: 200, headers: { "content-type": "application/json" } }));
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  vi.unstubAllGlobals();
});

describe("triângulos: pelo celular por padrão, presencial só quando pedido", () => {
  it("sem escolha pede mode=celular", async () => {
    await api.triangles("real");
    expect(modeParam(0)).toBe("celular");
  });
  it("com 'todos' pede mode=todos (inclui pernas presenciais)", async () => {
    await api.triangles("real", { route: "todos" });
    expect(modeParam(0)).toBe("todos");
  });
});
