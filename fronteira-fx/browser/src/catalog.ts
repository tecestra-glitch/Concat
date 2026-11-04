// Cotação pela resposta interna do próprio site: `POST https://www.westernunion.com/wuconnect/prices/catalog`,
// que o SPA chama quando o valor e o destino estão definidos. Lê o JSON que o site já devolve, sem clicar.
//
// Forma observada ao vivo (2026-11-04, só as chaves): a raiz tem `header_reply`, `response_status`, `sender`,
// `receiver` e `services_groups`; cada grupo de serviço traz `fund_out` / `fund_out_mnem` (recebimento) e uma
// lista de combinações (`pay_groups`, com o `fund_in` do pagamento). Os nomes dos valores dentro da combinação
// ainda não foram confirmados: a leitura procura por padrão e, se não achar, devolve null (o fluxo segue pelos cliques).
// `catalogShape` descreve só as CHAVES da resposta (sem valores), para a trilha de diagnóstico.

import { parseDecimalText } from "./decimal.js";
import type { Payment, Receive } from "./types.js";

export interface CatalogQuote {
  receive_amount_pyg: string;
  fee_brl: string | null;
  fee_before_discount_brl: string | null;
  exchange_rate: string | null;
  delivery: string | null;
  promo: string | null;
}

const MAX_LEAVES = 400;
const MAX_DEPTH = 9;

/** URL da resposta de cotação do site (só o caminho e o host da Western Union). */
export function isCatalogUrl(url: string): boolean {
  try {
    const u = new URL(url);
    return u.hostname.endsWith("westernunion.com") && u.pathname.includes("prices/catalog");
  } catch {
    return false;
  }
}

/** Valor enviado (sender.send_amount) no corpo JSON da requisição, ou null. */
export function catalogAmount(postData: string | null | undefined): string | null {
  if (!postData) return null;
  try {
    const data = JSON.parse(postData) as { sender?: { send_amount?: unknown } } | null;
    const v = data?.sender?.send_amount;
    if (typeof v === "string" && v.trim() !== "") return v.trim();
    if (typeof v === "number" && Number.isFinite(v)) return String(v);
  } catch {
    // corpo que não é JSON: não é a nossa requisição
  }
  return null;
}

export function sameAmount(a: string, b: string): boolean {
  const na = Number(a);
  const nb = Number(b);
  return Number.isFinite(na) && Number.isFinite(nb) && na === nb;
}

interface Leaf {
  path: string;
  key: string;
  value: string | number;
}

/** Campos escalares de um objeto e de seus filhos que não são arrays (um array é outra combinação). */
function ownLeaves(node: object, path = "", depth = 0, out: Leaf[] = []): Leaf[] {
  if (depth > 3 || out.length >= MAX_LEAVES) return out;
  for (const [k, v] of Object.entries(node)) {
    const p = path ? `${path}.${k}` : k;
    if (Array.isArray(v)) continue;
    if (v !== null && typeof v === "object") ownLeaves(v, p, depth + 1, out);
    else if (typeof v === "string" || typeof v === "number") out.push({ path: p, key: k, value: v });
  }
  return out;
}

const RECEIVE_TOKENS: Record<Receive, RegExp> = {
  bank_account: /^(BA|BANK|BANKACCOUNT|ACCOUNT|CONTA)$|BANK_?ACC|CONTA/i,
  cash_pickup: /^(AG|AGENT|CASH|PICKUP)$|CASH|DINHEIRO|AGENT|LOJA/i,
};
// Pix and bank transfer share the WU Pay tile on the site, so both accept its codes (WUPAY, WU_PAY, WU PAY).
const PAYMENT_TOKENS: Record<Payment, RegExp> = {
  pix: /PIX|WU[ _-]?PAY/i,
  bank_transfer: /TRANSF|BANK|WU[ _-]?PAY/i,
  card: /CARD|CARTAO|CARTÃO|CREDIT|DEBIT|^(CC|DC)$/i,
};

interface Ctx {
  out: string[];
  inn: string[];
}

function numericText(v: string | number): string | null {
  return parseDecimalText(String(v));
}

function firstNumeric(leaves: Leaf[], keyRe: RegExp, pathRe: RegExp | null, excludePath?: RegExp): string | null {
  for (const l of leaves) {
    if (!keyRe.test(l.key)) continue;
    if (pathRe && !pathRe.test(l.path)) continue;
    if (excludePath && excludePath.test(l.path)) continue;
    const v = numericText(l.value);
    if (v !== null) return v;
  }
  return null;
}

function exactNumeric(leaves: Leaf[], key: string): string | null {
  for (const l of leaves) {
    if (l.key !== key) continue;
    const v = numericText(l.value);
    if (v !== null) return v;
  }
  return null;
}

/**
 * Product codes only (fund_in, fund_out, service names as they come in the response): e.g. "fund_in=[WUPAY,CARD]".
 * No amounts, identifiers or free text are included, so the trail can show which codes the site uses.
 */
export function catalogCodes(node: unknown): string {
  const found = new Map<string, Set<string>>();
  const visit = (n: unknown, depth: number): void => {
    if (depth > MAX_DEPTH || n === null || typeof n !== "object") return;
    if (Array.isArray(n)) {
      for (const c of n) visit(c, depth + 1);
      return;
    }
    for (const [k, v] of Object.entries(n)) {
      if (/^(fund_in|fund_out|fund_out_mnem|service)$/.test(k) && typeof v === "string" && v.length <= 24) {
        const set = found.get(k) ?? new Set<string>();
        if (set.size < 12) set.add(v.toUpperCase());
        found.set(k, set);
      }
      visit(v, depth + 1);
    }
  };
  visit(node, 0);
  return [...found.entries()].map(([k, s]) => `${k}=[${[...s].join(",")}]`).join(";").slice(0, 600);
}

/** Quote for one combination node, when its context has the requested receive and payment and an amount. */
function quoteHere(leaves: Leaf[], ctx: Ctx, want: { receive: Receive; payment: Payment }): CatalogQuote | null {
  if (!ctx.out.some((t) => RECEIVE_TOKENS[want.receive].test(t))) return null;
  if (!ctx.inn.some((t) => PAYMENT_TOKENS[want.payment].test(t))) return null;
  // Field names seen live (2026-11-04, keys only): pay_groups[] carry receive_amount, fx_rate, gross_fee,
  // strike_gross_fee, strike_fx_rate and speed_indicator. The exact keys win; the patterns are the fallback.
  const received = exactNumeric(leaves, "receive_amount") ??
    firstNumeric(leaves, /amount|value|total|sum/i, /receiv|recipient|dest|payout|pay_out/i);
  if (received === null || Number(received) <= 0) return null;
  const fee = exactNumeric(leaves, "gross_fee") ??
    firstNumeric(leaves, /fee|tarifa|charge/i, null, /before|list|original|gross|discount|strike/i);
  const feeBefore = exactNumeric(leaves, "strike_gross_fee") ??
    firstNumeric(leaves, /fee|tarifa|charge/i, /before|list|original|gross/i);
  const rate = exactNumeric(leaves, "fx_rate") ?? firstNumeric(leaves, /rate|exchange|cambio|câmbio/i, null);
  const speed = leaves.find((l) => l.key === "speed_indicator" && typeof l.value === "string");
  const deliveryLeaf = speed ?? leaves.find((l) => typeof l.value === "string" && /deliver|eta|prazo|speed|time/i.test(l.key));
  // promo: text only ("100% de desconto 45.00 BRL"); a numeric field such as fee_before_discount_brl is not a promo
  const promoLeaf = leaves.find(
    (l) =>
      typeof l.value === "string" &&
      (/promo/i.test(l.key) || (/discount|desconto/i.test(l.key) && /[a-zà-ú]{3,}/i.test(l.value))),
  );
  return {
    receive_amount_pyg: received,
    fee_brl: fee,
    fee_before_discount_brl: feeBefore,
    exchange_rate: rate,
    delivery: typeof deliveryLeaf?.value === "string" ? deliveryLeaf.value : null,
    promo: typeof promoLeaf?.value === "string" ? promoLeaf.value : null,
  };
}

/**
 * Monta a cotação para o recebimento e o pagamento pedidos, ou null se a resposta não os mostra.
 * Percorre a árvore de cima para baixo levando o contexto dos pais: `fund_out` vem do grupo de serviço e
 * `fund_in` da combinação de pagamento (pay_groups). Uma combinação só vale com os dois e com um valor recebido.
 */
export function quoteFromCatalog(body: unknown, want: { receive: Receive; payment: Payment }): CatalogQuote | null {
  return walk(body, { out: [], inn: [] }, want, 0);
}

function walk(
  node: unknown,
  ctx: Ctx,
  want: { receive: Receive; payment: Payment },
  depth: number,
): CatalogQuote | null {
  if (depth > MAX_DEPTH || node === null || typeof node !== "object") return null;
  if (Array.isArray(node)) {
    for (const child of node) {
      const q = walk(child, ctx, want, depth + 1);
      if (q) return q;
    }
    return null;
  }
  const leaves = ownLeaves(node);
  const next: Ctx = {
    out: [...ctx.out, ...leaves.filter((l) => /fund_?out/i.test(l.path)).map((l) => String(l.value))],
    inn: [...ctx.inn, ...leaves.filter((l) => /fund_?in/i.test(l.path)).map((l) => String(l.value))],
  };
  const here = quoteHere(leaves, next, want);
  if (here) return here;
  for (const child of Object.values(node)) {
    const q = walk(child, next, want, depth + 1);
    if (q) return q;
  }
  return null;
}

/** Só a forma da resposta (nomes de chave e tipos, sem valores), para o diagnóstico na trilha. */
export function catalogShape(node: unknown): string {
  const text = shapeOf(node, 0);
  return text.length > 900 ? `${text.slice(0, 900)}…` : text;
}

function shapeOf(node: unknown, depth: number): string {
  if (depth > 9) return "…";
  if (node === null) return "null";
  if (Array.isArray(node)) return node.length === 0 ? "[0]" : `[${node.length}]<${shapeOf(node[0], depth + 1)}>`;
  if (typeof node === "object") {
    const entries = Object.entries(node).slice(0, 25);
    return `{${entries.map(([k, v]) => `${k}:${shapeOf(v, depth + 1)}`).join(",")}}`;
  }
  return typeof node;
}
