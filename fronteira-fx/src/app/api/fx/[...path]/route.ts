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
 *
 * Segurança (SEC-02 / SEC-04):
 * - só `/v1/...` é repassado (nunca `/mcp`, `/docs`, `/openapi.json`); segmentos `.`/`..` (mesmo
 *   codificados) ou com barra são recusados com 400, e a URL final é conferida contra a base;
 * - a chave só vai quando o frontend está protegido (`FX_BASIC_AUTH` ou `FX_FRONTEND_PROTECTED=1`, ver
 *   `src/lib/server/frontend-auth.ts`); sem proteção as mutações são recusadas com 403;
 * - mutações cross-site (`Sec-Fetch-Site` diferente de same-origin, ou `Origin` de outro host) → 403.
 */
import { BASIC_REALM, frontendGate } from "@/lib/server/frontend-auth";

type Ctx = { params: Promise<{ path: string[] }> };

/** Único prefixo público do backend que o navegador pode alcançar. */
const API_PREFIX = "v1";

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

/** Decodifica até estabilizar (cobre `%252e`): o que importa é o que algum salto adiante pode ver. */
function fullyDecoded(segment: string): string {
  let current = segment;
  for (let i = 0; i < 3; i++) {
    let next: string;
    try {
      next = decodeURIComponent(current);
    } catch {
      return current;
    }
    if (next === current) break;
    current = next;
  }
  return current;
}

/** `null` quando o caminho é aceitável; senão o status e o motivo da recusa. */
function rejectPath(path: string[]): { status: number; detail: string } | null {
  if (path[0] !== API_PREFIX || path.length < 2) return { status: 404, detail: "Rota fora da API pública (/api/fx/v1/...)." };
  for (const segment of path) {
    const plain = fullyDecoded(segment);
    if (plain === "" || plain === "." || plain === ".." || /[/\\]/.test(plain)) {
      return { status: 400, detail: "Caminho inválido: segmentos vazios, '.', '..' ou com barra não são aceitos." };
    }
  }
  return null;
}

/** Monta a URL e confere que ela continua sob `${base}/v1/` depois da normalização do `URL`. */
function buildUpstreamUrl(base: string, path: string[], search: string): string | null {
  const encoded = path.map((segment) => encodeURIComponent(segment)).join("/");
  let url: URL;
  let root: URL;
  try {
    url = new URL(`${base}/${encoded}${search}`);
    root = new URL(base);
  } catch {
    return null;
  }
  const prefix = `${root.pathname.replace(/\/+$/, "")}/${API_PREFIX}/`;
  if (url.origin !== root.origin || !url.pathname.startsWith(prefix)) return null;
  return url.toString();
}

const SAFE_METHODS = new Set(["GET", "HEAD"]);

/** SEC-04: uma mutação só vale vinda do próprio app (Fetch Metadata e, na falta dele, `Origin`). */
function isCrossSite(req: Request): boolean {
  const site = req.headers.get("sec-fetch-site");
  if (site && site !== "same-origin" && site !== "none") return true;
  const origin = req.headers.get("origin");
  if (!origin) return false;
  const host = req.headers.get("x-forwarded-host") ?? req.headers.get("host") ?? new URL(req.url).host;
  try {
    return new URL(origin).host !== host.split(",")[0].trim();
  } catch {
    return true;
  }
}

function buildRequestHeaders(req: Request, withKey: boolean): Headers {
  const headers = new Headers();
  for (const name of FORWARD_REQUEST_HEADERS) {
    const value = req.headers.get(name);
    if (value) headers.set(name, value);
  }
  const key = (process.env.FX_API_KEY ?? "").trim();
  if (key && withKey) headers.set("x-api-key", key);
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

  const segments = path ?? [];
  const refused = rejectPath(segments);
  if (refused) return json(refused.status, { detail: refused.detail });
  const search = new URL(req.url).search;
  const url = buildUpstreamUrl(base, segments, search);
  if (!url) return json(400, { detail: "Caminho inválido para a API." });

  const method = req.method.toUpperCase();
  const mutation = !SAFE_METHODS.has(method);
  if (mutation && isCrossSite(req)) {
    return json(403, { detail: "Mutação recusada: a requisição não veio do próprio app (origem cruzada)." });
  }
  const gate = frontendGate(req);
  if (gate.kind === "unauthenticated") {
    return new Response(JSON.stringify({ detail: "Autenticação necessária." }), {
      status: 401,
      headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store", "www-authenticate": BASIC_REALM },
    });
  }
  const keyConfigured = (process.env.FX_API_KEY ?? "").trim() !== "";
  if (keyConfigured && gate.kind === "unprotected" && mutation) {
    return json(403, {
      detail:
        "Proxy sem proteção: a chave da API só é usada com o frontend protegido. Defina FX_BASIC_AUTH=usuario:senha " +
        "ou, se o frontend já é privado (loopback, VPN, Deployment Protection), FX_FRONTEND_PROTECTED=1.",
    });
  }
  const init: RequestInit = {
    method,
    headers: buildRequestHeaders(req, gate.kind === "trusted"),
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
