/**
 * SEC-1 do pregão: os fetchers do pregão vão pelo proxy `/api/fx` (be1a0f0), e o proxy da principal fecha o relé
 * aberto. Aqui se confere, com as URLs que o pregão monta, que as leituras do pregão passam e que o resto não.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { GET, POST } from "@/app/api/fx/[...path]/route";
import { fetchCandles, fetchSessions, fetchStats } from "@/lib/pregao/api";

const UPSTREAM = "http://api:8000";
const KEY = "K-SECRETA";
const EVIL = { origin: "https://evil.example", "sec-fetch-site": "cross-site" };
const KEY_A = "chaco:CDE:USD/PYG:cash:@chaco-cde-centro";

const ctxOf = (url: string) => {
  const path = new URL(url).pathname.replace(/^\/api\/fx\/?/, "");
  return { params: Promise.resolve({ path: path === "" ? [] : path.split("/").map(decodeURIComponent) }) };
};
const json = (body: unknown) => new Response(JSON.stringify(body), { status: 200, headers: { "content-type": "application/json" } });

type Upstream = (url: string, init?: RequestInit) => Promise<Response>;
let upstream: ReturnType<typeof vi.fn<Upstream>>;

beforeEach(() => {
  vi.stubEnv("FX_API_URL", UPSTREAM);
  vi.stubEnv("FX_API_KEY", KEY);
  vi.stubEnv("FX_FRONTEND_PROTECTED", "1");
  vi.stubEnv("FX_BASIC_AUTH", "");
  upstream = vi.fn<Upstream>();
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

/** Faz o `fetch` do navegador (relativo, `/api/fx/...`) atravessar o handler do proxy de verdade. */
function browserThroughProxy(): string[] {
  const seen: string[] = [];
  vi.stubGlobal("fetch", async (input: string | URL | Request, init?: RequestInit) => {
    const target = String(input);
    if (target.startsWith(UPSTREAM)) return upstream(target, init);
    const url = new URL(target, "http://localhost:3000").toString();
    seen.push(url);
    return GET(new Request(url, init), ctxOf(url));
  });
  return seen;
}

describe("proxy /api/fx com as rotas do pregão (SEC-1)", () => {
  it("as três leituras do pregão chegam ao backend em /v1/..., com a query intacta", async () => {
    const seen = browserThroughProxy();
    upstream
      .mockResolvedValueOnce(json({ key: KEY_A, tf: "1h", candles: [], data_mode: "real" }))
      .mockResolvedValueOnce(json([]))
      .mockResolvedValueOnce(json([]));
    await expect(fetchCandles("real", KEY_A, "1h", { limit: 50 })).resolves.toMatchObject({ key: KEY_A, candles: [] });
    await expect(fetchStats("real", [KEY_A])).resolves.toEqual([]);
    await expect(fetchSessions("real")).resolves.toEqual([]);

    expect(seen.map((u) => new URL(u).pathname)).toEqual(["/api/fx/v1/candles", "/api/fx/v1/pregao/stats", "/api/fx/v1/pregao/sessions"]);
    const sent = upstream.mock.calls.map(([u]) => new URL(u));
    expect(sent.map((u) => u.origin + u.pathname)).toEqual([`${UPSTREAM}/v1/candles`, `${UPSTREAM}/v1/pregao/stats`, `${UPSTREAM}/v1/pregao/sessions`]);
    expect(sent[0].searchParams.get("key")).toBe(KEY_A);
    expect(sent[0].searchParams.get("data_mode")).toBe("real");
    expect(sent[1].searchParams.get("keys")).toBe(KEY_A);
  });

  it("/api/fx/mcp e /api/fx/openapi.json dão 404 sem tocar o backend, em GET e POST", async () => {
    // `/api/fx/v1/../mcp` chega aqui já normalizado pelo `URL` como `/api/fx/mcp`: cai no mesmo 404.
    for (const path of ["mcp", "openapi.json", "docs", "redoc", "v1/../mcp"]) {
      const url = `http://localhost:3000/api/fx/${path}`;
      const get = await GET(new Request(url, { headers: EVIL }), ctxOf(url));
      const post = await POST(new Request(url, { method: "POST", body: '{"jsonrpc":"2.0","id":1,"method":"tools/list"}', headers: { "content-type": "application/json" } }), ctxOf(url));
      expect([get.status, post.status], path).toEqual([404, 404]);
    }
    expect(upstream).not.toHaveBeenCalled();
  });

  it("um segmento '..' entregue em params não escapa de /v1 (400, sem chamar o backend)", async () => {
    vi.stubGlobal("fetch", upstream);
    const res = await GET(new Request("http://localhost:3000/api/fx/v1/candles"), { params: Promise.resolve({ path: ["v1", "..", "docs"] }) });
    expect(res.status).toBe(400);
    expect(upstream).not.toHaveBeenCalled();
  });

  it("mutação vinda de outro site dá 403 e não leva a chave a lugar nenhum", async () => {
    vi.stubGlobal("fetch", upstream);
    for (const path of ["v1/rag/documents", "v1/sources/chaco/poll", "v1/candles"]) {
      const url = `http://localhost:3000/api/fx/${path}`;
      const res = await POST(new Request(url, { method: "POST", body: "{}", headers: { ...EVIL, "content-type": "application/json" } }), ctxOf(url));
      expect(res.status, path).toBe(403);
    }
    expect(upstream).not.toHaveBeenCalled();
  });

  it("sem frontend protegido, a leitura do pregão vai sem a chave e a escrita é recusada", async () => {
    vi.stubEnv("FX_FRONTEND_PROTECTED", "");
    vi.stubGlobal("fetch", upstream);
    upstream.mockResolvedValue(json([]));
    const read = "http://localhost:3000/api/fx/v1/pregao/sessions";
    expect((await GET(new Request(read), ctxOf(read))).status).toBe(200);
    expect(new Headers(upstream.mock.calls[0][1]?.headers).has("x-api-key")).toBe(false);
    upstream.mockClear();
    const write = "http://localhost:3000/api/fx/v1/journal";
    const res = await POST(new Request(write, { method: "POST", body: "{}", headers: { "sec-fetch-site": "same-origin" } }), ctxOf(write));
    expect(res.status).toBe(403);
    expect(upstream).not.toHaveBeenCalled();
  });
});
