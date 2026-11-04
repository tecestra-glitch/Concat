import { describe, expect, it, vi } from "vitest";
import { probeStreamOff } from "./stream-probe";

function fakeFetch(status: number) {
  return vi.fn(async (_url: RequestInfo | URL, init?: RequestInit) => {
    expect(init?.signal).toBeInstanceOf(AbortSignal);
    return new Response(null, { status });
  });
}

describe("probeStreamOff", () => {
  it("404 quer dizer stream desligado na API (serverless)", async () => {
    const f = fakeFetch(404);
    await expect(probeStreamOff("/api/fx/v1/stream", f)).resolves.toBe(true);
    expect(f).toHaveBeenCalledTimes(1);
    expect(f.mock.calls[0][1]?.headers).toMatchObject({ accept: "text/event-stream" });
  });

  it("200 (stream existe) e erros de servidor não desligam o stream", async () => {
    await expect(probeStreamOff("/s", fakeFetch(200))).resolves.toBe(false);
    await expect(probeStreamOff("/s", fakeFetch(502))).resolves.toBe(false);
    await expect(probeStreamOff("/s", fakeFetch(410))).resolves.toBe(false);
  });

  it("falha de rede não desliga o stream", async () => {
    const f = vi.fn<typeof fetch>(async () => {
      throw new TypeError("network");
    });
    await expect(probeStreamOff("/s", f)).resolves.toBe(false);
  });

  it("aborta a conexão logo depois de ler o status (não fica um stream aberto)", async () => {
    let signal: AbortSignal | undefined;
    const f = vi.fn(async (_u: RequestInfo | URL, init?: RequestInit) => {
      signal = init?.signal ?? undefined;
      return new Response(null, { status: 200 });
    });
    await probeStreamOff("/s", f);
    expect(signal?.aborted).toBe(true);
  });
});
