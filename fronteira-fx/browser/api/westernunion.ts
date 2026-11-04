import type { IncomingMessage, ServerResponse } from "node:http";
import { handleWesternUnion } from "../src/handler.js";

type VercelRequest = IncomingMessage & { body?: unknown };

// Vercel's Node runtime parses JSON bodies (application/json) into `req.body`; a raw string is parsed here.
function jsonBody(raw: unknown): unknown {
  if (typeof raw !== "string") return raw;
  try {
    return JSON.parse(raw) as unknown;
  } catch {
    return undefined;
  }
}

export default async function handler(req: VercelRequest, res: ServerResponse): Promise<void> {
  const result = await handleWesternUnion(
    {
      method: req.method,
      authorization: req.headers.authorization,
      body: jsonBody(req.body),
    },
    process.env,
  );
  res.statusCode = result.status;
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  res.setHeader("Cache-Control", "no-store");
  for (const [name, value] of Object.entries(result.headers ?? {})) res.setHeader(name, value);
  res.end(JSON.stringify(result.body));
}
