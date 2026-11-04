// Teste real (uma visita à Western Union). Chama a função como a Vercel: o default export de api/westernunion.ts
// recebe req/res. Uso local:
//   CHROMIUM_EXECUTABLE_PATH=/caminho/chrome-headless-shell pnpm smoke
// Opcional: SMOKE_OUT_DIR=<pasta> grava a captura de tela (PNG). O segredo é gerado para esta execução e não é impresso.
import { randomBytes } from "node:crypto";
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import type { IncomingMessage, ServerResponse } from "node:http";
import handler from "../api/westernunion.js";

const secret = randomBytes(24).toString("hex");
process.env.BROWSER_SECRET = secret;

const body = { amount_brl: "5000", payment: "pix", receive: "bank_account", screenshot: true };

const headers: Record<string, string> = {};
let statusCode = 0;
let payload = "";
const req = {
  method: "POST",
  headers: { authorization: `Bearer ${secret}`, "content-type": "application/json" },
  body,
} as unknown as IncomingMessage & { body: unknown };
const res = {
  get statusCode() {
    return statusCode;
  },
  set statusCode(v: number) {
    statusCode = v;
  },
  setHeader(name: string, value: string) {
    headers[name.toLowerCase()] = value;
  },
  end(chunk: string) {
    payload = chunk;
  },
} as unknown as ServerResponse;

const started = Date.now();
await handler(req, res);
const seconds = ((Date.now() - started) / 1000).toFixed(1);

console.log(`HTTP ${statusCode} em ${seconds} s`);
const parsed = JSON.parse(payload) as Record<string, unknown> & {
  screenshot_png_b64?: string;
  scenario?: Record<string, unknown> | null;
};
console.log(`status: ${String(parsed.status)}`);
console.log(`message: ${String(parsed.message)}`);
console.log(`trail: ${JSON.stringify(parsed.trail)}`);
if (parsed.scenario) {
  console.log(`scenario keys: ${Object.keys(parsed.scenario).join(", ")}`);
  console.log(`scenario: ${JSON.stringify({ ...parsed.scenario, summary_text: undefined })}`);
}
if (parsed.screenshot_png_b64) {
  const dir = process.env.SMOKE_OUT_DIR;
  if (dir) {
    mkdirSync(dir, { recursive: true });
    const file = join(dir, `wu_smoke_${Date.now()}.png`);
    writeFileSync(file, Buffer.from(parsed.screenshot_png_b64, "base64"));
    console.log(`screenshot: ${file}`);
  } else {
    console.log(`screenshot: ${parsed.screenshot_png_b64.length} chars base64 (defina SMOKE_OUT_DIR para salvar)`);
  }
}
