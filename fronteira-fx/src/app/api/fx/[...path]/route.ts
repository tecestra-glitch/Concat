/**
 * Proxy server-side para a API do Fronteira FX (D5).
 *
 * O browser fala com `/api/fx/...`; este handler repassa para `FX_API_URL` e
 * injeta `X-API-Key` a partir de `FX_API_KEY`. As duas variáveis são lidas
 * apenas no servidor (nunca `NEXT_PUBLIC_*`) e a chave nunca aparece em
 * resposta, cabeçalho de retorno ou log.
 *
 * Sem `export const dynamic`: com `cacheComponents: true` o Next rejeita configuração de segmento
 * de rota. O handler já é dinâmico por ler a requisição (URL, cabeçalhos, corpo), e toda resposta
 * sai com `cache-control: no-store` salvo quando o backend define o próprio.
 */

type Ctx = { params: Promise<{ path: string[] }> };

/** Cabeçalhos da requisição do browser que fazem sentido chegar ao backend. */
const FORWARD_REQUEST_HEADERS = ["content-type", "accept", "last-event-id", "if-none-match", "if-modified-since"];

/** Cabeçalhos da resposta do backend que podem voltar ao browser (allowlist). */
const FORWARD_RESPONSE_HEADERS = [
  "content-type",
  "cache-control",
  "etag",
  "last-modified",
  "location",
  "retry-after",
  "x-request-id",
  "vary",
  "content-disposition",
];

const METHODS_WITHOUT_BODY = new Set(["GET", "HEAD", "DELETE"]);

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" },
  });
}

function upstreamBase(): string {
  return (process.env.FX_API_URL ?? "").trim().replace(/\/+$/, "");
}

function buildUpstreamUrl(base: string, path: string[], search: string): string {
  const encoded = path.map((segment) => encodeURIComponent(segment)).join("/");
  return `${base}/${encoded}${search}`;
}

function buildRequestHeaders(req: Request): Headers {
  const headers = new Headers();
  for (const name of FORWARD_REQUEST_HEADERS) {
    const value = req.headers.get(name);
    if (value) headers.set(name, value);
  }
  const key = (process.env.FX_API_KEY ?? "").trim();
  if (key) headers.set("x-api-key", key);
  return headers;
}

function buildResponseHeaders(upstream: Response): Headers {
  const headers = new Headers();
  for (const name of FORWARD_RESPONSE_HEADERS) {
    const value = upstream.headers.get(name);
    if (value) headers.set(name, value);
  }
  if (!headers.has("cache-control")) headers.set("cache-control", "no-store");
  return headers;
}

function isEventStream(upstream: Response): boolean {
  return (upstream.headers.get("content-type") ?? "").toLowerCase().includes("text/event-stream");
}

async function proxy(req: Request, ctx: Ctx): Promise<Response> {
  const { path } = await ctx.params;
  const base = upstreamBase();
  if (!base) {
    return json(503, { detail: "Backend não configurado: defina FX_API_URL no servidor." });
  }

  const search = new URL(req.url).search;
  const url = buildUpstreamUrl(base, path ?? [], search);
  const method = req.method.toUpperCase();
  const init: RequestInit = {
    method,
    headers: buildRequestHeaders(req),
    cache: "no-store",
    redirect: "manual",
    signal: req.signal,
  };
  if (!METHODS_WITHOUT_BODY.has(method)) {
    init.body = await req.text();
  }

  let upstream: Response;
  try {
    upstream = await fetch(url, init);
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    // Nunca registrar a chave: redige qualquer ocorrência antes de logar.
    const key = (process.env.FX_API_KEY ?? "").trim();
    const safe = key ? message.split(key).join("[redacted]") : message;
    console.error(`[api/fx] ${method} /${(path ?? []).join("/")} falhou: ${safe}`);
    return json(502, { detail: "Backend indisponível." });
  }

  const headers = buildResponseHeaders(upstream);

  if (isEventStream(upstream)) {
    headers.set("content-type", "text/event-stream");
    headers.set("cache-control", "no-cache, no-transform");
    headers.set("x-accel-buffering", "no");
    return new Response(upstream.body, { status: upstream.status, headers });
  }

  if (upstream.status === 204 || upstream.status === 304) {
    return new Response(null, { status: upstream.status, headers });
  }

  return new Response(upstream.body, { status: upstream.status, headers });
}

export async function GET(req: Request, ctx: Ctx): Promise<Response> {
  return proxy(req, ctx);
}

export async function POST(req: Request, ctx: Ctx): Promise<Response> {
  return proxy(req, ctx);
}

export async function PATCH(req: Request, ctx: Ctx): Promise<Response> {
  return proxy(req, ctx);
}

export async function DELETE(req: Request, ctx: Ctx): Promise<Response> {
  return proxy(req, ctx);
}
