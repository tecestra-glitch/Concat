import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as route from "@/app/api/fx/[...path]/route";

const { DELETE, GET, PATCH, POST } = route;

const UPSTREAM = "http://backend.internal:8000";
const KEY = "chave-super-secreta-nunca-no-browser";
const ctx = (...path: string[]) => ({ params: Promise.resolve({ path }) });
const json = (body: unknown, init: ResponseInit = {}) =>
  new Response(JSON.stringify(body), { status: 200, headers: { "content-type": "application/json" }, ...init });

let fetchMock: ReturnType<typeof vi.fn>;
const lastCall = () => fetchMock.mock.calls[0] as [string, RequestInit];

beforeEach(() => {
  vi.stubEnv("FX_API_URL", `${UPSTREAM}/`); // trailing slash must not produce a double slash
  vi.stubEnv("FX_API_KEY", KEY);
  // The operator states the frontend is private (loopback, VPN, Vercel Deployment Protection): key injected.
  vi.stubEnv("FX_FRONTEND_PROTECTED", "1");
  vi.stubEnv("FX_BASIC_AUTH", "");
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
});

describe("proxy /api/fx/[...path]", () => {
  it("declares no route-segment config (forbidden by cacheComponents) and answers with no-store", async () => {
    // With `cacheComponents: true` Next rejects `export const dynamic/revalidate/fetchCache`;
    // the handler is dynamic because it reads the request, and every answer is marked no-store.
    for (const name of ["dynamic", "revalidate", "fetchCache", "runtime"]) expect(name in route).toBe(false);
    fetchMock.mockResolvedValue(json([]));
    const res = await GET(new Request("http://localhost:3000/api/fx/v1/sources"), ctx("v1", "sources"));
    expect(res.headers.get("cache-control")).toBe("no-store");
  });

  it("builds the upstream URL from the path and forwards the query string (incl. data_mode)", async () => {
    fetchMock.mockResolvedValue(json([]));
    const res = await GET(new Request("http://localhost:3000/api/fx/v1/quotes?city=CDE&amount=5000&data_mode=simulation"), ctx("v1", "quotes"));
    expect(res.status).toBe(200);
    const [url, init] = lastCall();
    expect(String(url)).toBe(`${UPSTREAM}/v1/quotes?city=CDE&amount=5000&data_mode=simulation`);
    expect(init.method).toBe("GET");
    expect(new Headers(init.headers).get("x-api-key")).toBe(KEY);
    expect(await res.json()).toEqual([]);
  });

  it("forwards body and content-type on POST and PATCH, and the method on DELETE", async () => {
    fetchMock.mockResolvedValue(json({ ok: true }, { status: 201 }));
    const body = JSON.stringify({ source_id: "chaco", params: { amount: "5000" } });
    const post = await POST(new Request("http://localhost:3000/api/fx/v1/quotes/request", { method: "POST", body, headers: { "content-type": "application/json" } }), ctx("v1", "quotes", "request"));
    expect(post.status).toBe(201);
    let [url, init] = lastCall();
    expect(String(url)).toBe(`${UPSTREAM}/v1/quotes/request`);
    expect(init.method).toBe("POST");
    expect(new Headers(init.headers).get("content-type")).toBe("application/json");
    expect(await new Response(init.body as BodyInit).text()).toBe(body);

    fetchMock.mockClear();
    fetchMock.mockResolvedValue(json({ id: "r1" }));
    await PATCH(new Request("http://localhost:3000/api/fx/v1/alerts/rules/r1", { method: "PATCH", body: '{"enabled":false}', headers: { "content-type": "application/json" } }), ctx("v1", "alerts", "rules", "r1"));
    [url, init] = lastCall();
    expect(String(url)).toBe(`${UPSTREAM}/v1/alerts/rules/r1`);
    expect(init.method).toBe("PATCH");
    expect(await new Response(init.body as BodyInit).text()).toBe('{"enabled":false}');

    fetchMock.mockClear();
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
    const del = await DELETE(new Request("http://localhost:3000/api/fx/v1/alerts/rules/r1", { method: "DELETE" }), ctx("v1", "alerts", "rules", "r1"));
    expect(del.status).toBe(204);
    expect(lastCall()[1].method).toBe("DELETE");
  });

  it("passes the upstream status through, including 410 Gone for an expired cursor", async () => {
    for (const status of [404, 409, 410, 429]) {
      fetchMock.mockReset();
      fetchMock.mockResolvedValue(json({ detail: `status ${status}` }, { status }));
      const res = await GET(new Request("http://localhost:3000/api/fx/v1/stream?cursor=old"), ctx("v1", "stream"));
      expect(res.status).toBe(status);
      expect(await res.json()).toEqual({ detail: `status ${status}` });
    }
  });

  it("streams SSE: keeps text/event-stream, disables caching and forwards Last-Event-ID", async () => {
    const encoder = new TextEncoder();
    const stream = new ReadableStream<Uint8Array>({
      start(c) {
        c.enqueue(encoder.encode("id: 1\nevent: heartbeat\ndata: {}\n\n"));
        c.close();
      },
    });
    fetchMock.mockResolvedValue(new Response(stream, { status: 200, headers: { "content-type": "text/event-stream", "transfer-encoding": "chunked", connection: "keep-alive" } }));
    const res = await GET(new Request("http://localhost:3000/api/fx/v1/stream", { headers: { accept: "text/event-stream", "last-event-id": "abc" } }), ctx("v1", "stream"));
    const [, init] = lastCall();
    const sent = new Headers(init.headers);
    expect(sent.get("last-event-id")).toBe("abc");
    expect(sent.get("accept")).toBe("text/event-stream");
    expect(res.status).toBe(200);
    expect(res.headers.get("content-type")).toBe("text/event-stream");
    expect(res.headers.get("cache-control")).toMatch(/no-cache|no-store/);
    expect(res.headers.get("transfer-encoding")).toBeNull();
    expect(res.headers.get("connection")).toBeNull();
    expect(await res.text()).toBe("id: 1\nevent: heartbeat\ndata: {}\n\n");
  });

  it("never exposes the API key in responses or logs", async () => {
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    fetchMock.mockResolvedValue(new Response("nope", { status: 401, headers: { "x-api-key": KEY, "www-authenticate": `ApiKey ${KEY}` } }));
    const res = await GET(new Request("http://localhost:3000/api/fx/v1/sources"), ctx("v1", "sources"));
    expect(res.status).toBe(401);
    for (const [, v] of res.headers) expect(v).not.toContain(KEY);
    expect(await res.text()).not.toContain(KEY);

    fetchMock.mockRejectedValue(new Error(`connect ECONNREFUSED ${KEY}`));
    const down = await GET(new Request("http://localhost:3000/api/fx/v1/sources"), ctx("v1", "sources"));
    expect(down.status).toBe(502);
    expect(await down.text()).not.toContain(KEY);
    for (const call of errorSpy.mock.calls) expect(JSON.stringify(call)).not.toContain(KEY);
  });

  it("answers 503 without calling upstream when FX_API_URL is not configured", async () => {
    vi.stubEnv("FX_API_URL", "");
    const res = await GET(new Request("http://localhost:3000/api/fx/v1/health"), ctx("v1", "health"));
    expect(res.status).toBe(503);
    expect(fetchMock).not.toHaveBeenCalled();
    expect((await res.json()).detail).toMatch(/FX_API_URL/);
  });

  it("omits X-API-Key when FX_API_KEY is empty (local backend without key)", async () => {
    vi.stubEnv("FX_API_KEY", "");
    fetchMock.mockResolvedValue(json({ status: "ok" }));
    await GET(new Request("http://localhost:3000/api/fx/v1/health"), ctx("v1", "health"));
    expect(new Headers(lastCall()[1].headers).has("x-api-key")).toBe(false);
  });

  it("only forwards /v1: /mcp, /docs and /openapi.json never receive the key (SEC-02)", async () => {
    fetchMock.mockResolvedValue(json({}));
    for (const path of [["mcp"], ["docs"], ["openapi.json"], ["redoc"], [], ["v1"], ["v2", "sources"]]) {
      const res = await POST(new Request(`http://localhost:3000/api/fx/${path.join("/")}`, { method: "POST", body: "{}" }), ctx(...path));
      expect(res.status, path.join("/")).toBe(404);
    }
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("rejects dot segments, encoded or not, and segments carrying a slash (no escape from /v1)", async () => {
    fetchMock.mockResolvedValue(json({}));
    const cases = [["v1", "..", "mcp"], ["v1", ".", "sources"], ["v1", "%2e%2e", "mcp"], ["v1", ".%2E", "admin"], ["v1", "evidence", "ev/../admin"], ["v1", "evidence", "a\\b"], ["v1", "", "mcp"]];
    for (const path of cases) {
      const res = await GET(new Request("http://localhost:3000/api/fx/v1/x"), ctx(...path));
      expect(res.status, path.join("|")).toBe(400);
    }
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("keeps the upstream path under the configured base path", async () => {
    vi.stubEnv("FX_API_URL", "https://edge.example/fx/");
    fetchMock.mockResolvedValue(json([]));
    await GET(new Request("http://localhost:3000/api/fx/v1/evidence/ev-1"), ctx("v1", "evidence", "ev-1"));
    expect(String(lastCall()[0])).toBe("https://edge.example/fx/v1/evidence/ev-1");
  });

  it("never injects the key when the frontend is not declared protected; mutations are refused (SEC-02)", async () => {
    vi.stubEnv("FX_FRONTEND_PROTECTED", "");
    fetchMock.mockResolvedValue(json([]));
    await GET(new Request("http://localhost:3000/api/fx/v1/sources"), ctx("v1", "sources"));
    expect(new Headers(lastCall()[1].headers).has("x-api-key")).toBe(false);
    fetchMock.mockClear();
    const res = await POST(new Request("http://localhost:3000/api/fx/v1/journal", { method: "POST", body: "{}" }), ctx("v1", "journal"));
    expect(res.status).toBe(403);
    expect((await res.json()).detail).toMatch(/FX_BASIC_AUTH|FX_FRONTEND_PROTECTED/);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("with FX_BASIC_AUTH the key only goes with valid credentials", async () => {
    vi.stubEnv("FX_FRONTEND_PROTECTED", "");
    vi.stubEnv("FX_BASIC_AUTH", "eu:senha-forte");
    fetchMock.mockResolvedValue(json([]));
    const anon = await GET(new Request("http://localhost:3000/api/fx/v1/sources"), ctx("v1", "sources"));
    expect(anon.status).toBe(401);
    expect(anon.headers.get("www-authenticate")).toMatch(/^Basic /);
    const wrong = await GET(new Request("http://localhost:3000/api/fx/v1/sources", { headers: { authorization: `Basic ${btoa("eu:errada")}` } }), ctx("v1", "sources"));
    expect(wrong.status).toBe(401);
    expect(fetchMock).not.toHaveBeenCalled();
    const ok = await GET(new Request("http://localhost:3000/api/fx/v1/sources", { headers: { authorization: `Basic ${btoa("eu:senha-forte")}` } }), ctx("v1", "sources"));
    expect(ok.status).toBe(200);
    const sent = new Headers(lastCall()[1].headers);
    expect(sent.get("x-api-key")).toBe(KEY);
    expect(sent.has("authorization")).toBe(false);
  });

  it("refuses cross-site mutations (CSRF, SEC-04) and accepts same-origin ones", async () => {
    fetchMock.mockResolvedValue(json({ ok: true }));
    const cross = await POST(new Request("http://localhost:3000/api/fx/v1/watch/run/chaco", { method: "POST", headers: { "sec-fetch-site": "cross-site" } }), ctx("v1", "watch", "run", "chaco"));
    expect(cross.status).toBe(403);
    const foreign = await DELETE(new Request("http://localhost:3000/api/fx/v1/alerts/rules/r1", { method: "DELETE", headers: { origin: "https://evil.example" } }), ctx("v1", "alerts", "rules", "r1"));
    expect(foreign.status).toBe(403);
    expect(fetchMock).not.toHaveBeenCalled();
    const same = await POST(new Request("http://localhost:3000/api/fx/v1/watch/run/chaco", { method: "POST", headers: { "sec-fetch-site": "same-origin", origin: "http://localhost:3000" } }), ctx("v1", "watch", "run", "chaco"));
    expect(same.status).toBe(200);
    // GET stays readable cross-site only as far as the browser allows (no key-bearing side effects)
    const read = await GET(new Request("http://localhost:3000/api/fx/v1/sources", { headers: { "sec-fetch-site": "cross-site" } }), ctx("v1", "sources"));
    expect(read.status).toBe(200);
  });
});
