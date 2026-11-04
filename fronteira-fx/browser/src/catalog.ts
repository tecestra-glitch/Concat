// Cotação pela resposta interna do próprio site: `POST https://www.westernunion.com/wuconnect/prices/catalog`,
// que o SPA chama quando o valor e o destino estão definidos. Lê o JSON que o site já devolve, sem clicar.
//
// ATENÇÃO: o formato exato da resposta ainda não foi verificado ao vivo. O que se sabe (docs/adapters.md): o corpo
// da requisição tem `sender{cty_iso2_ext,curr_iso3,send_amount}` e `receiver{...}`, e a resposta traz
// `services_groups[].pay_groups[]` com preços por combinação fund_in/fund_out. Por isso a leitura é tolerante:
// procura os nomes de campo por padrão, exige o recebimento e o pagamento pedidos e, se não achar, devolve null
// (o fluxo segue pelos cliques). `catalogShape` descreve só as CHAVES da resposta, para o próximo ajuste.

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

const MAX_NODES = 5_000;
const MAX_LEAVES = 400;

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

function leavesOf(node: unknown, path = "", depth = 0, out: Leaf[] = []): Leaf[] {
  if (depth > 8 || out.length >= MAX_LEAVES) return out;
  if (Array.isArray(node)) {
    node.forEach((v, i) => leavesOf(v, `${path}[${i}]`, depth + 1, out));
  } else if (node !== null && typeof node === "object") {
    for (const [k, v] of Object.entries(node)) leavesOf(v, path ? `${path}.${k}` : k, depth + 1, out);
  } else if (typeof node === "string" || typeof node === "number") {
    const key = path.split(/[.[\]]/).filter(Boolean).pop() ?? "";
    out.push({ path, key, value: node });
  }
  return out;
}

/** Objetos do JSON, filhos antes dos pais: a combinação mais específica é avaliada primeiro. */
function* objectsPostOrder(node: unknown, depth = 0): Generator<unknown> {
  if (depth > 8) return;
  if (Array.isArray(node)) {
    for (const v of node) yield* objectsPostOrder(v, depth + 1);
  } else if (node !== null && typeof node === "object") {
    for (const v of Object.values(node)) yield* objectsPostOrder(v, depth + 1);
    yield node;
  }
}

const RECEIVE_TOKENS: Record<Receive, RegExp> = {
  bank_account: /^(BA|BANK|BANKACCOUNT|ACCOUNT|CONTA)$|BANK_?ACC|CONTA/i,
  cash_pickup: /^(AG|AGENT|CASH|PICKUP)$|CASH|DINHEIRO|AGENT|LOJA/i,
};
const PAYMENT_TOKENS: Record<Payment, RegExp> = {
  pix: /PIX|WUPAY/i,
  bank_transfer: /TRANSF|BANK|WUPAY/i,
  card: /CARD|CARTAO|CARTÃO|CREDIT|DEBIT|^(CC|DC)$/i,
};

function numericText(v: string | number): string | null {
  return parseDecimalText(String(v));
}

/** Monta a cotação para o recebimento e o pagamento pedidos, ou null se a resposta não os mostra. */
export function quoteFromCatalog(
  body: unknown,
  want: { receive: Receive; payment: Payment },
): CatalogQuote | null {
  let visited = 0;
  for (const obj of objectsPostOrder(body)) {
    if (++visited > MAX_NODES) break;
    // Only the object's own fields: a leaf under an array belongs to another combination, so it is left out
    // (otherwise a parent object would mix fund_in and fund_out from different pay groups).
    const leaves = leavesOf(obj).filter((l) => !l.path.includes("["));
    const outTokens = leaves.filter((l) => /fund_?out/i.test(l.path)).map((l) => String(l.value));
    const inTokens = leaves.filter((l) => /fund_?in/i.test(l.path)).map((l) => String(l.value));
    if (outTokens.length === 0 || inTokens.length === 0) continue;
    if (!outTokens.some((t) => RECEIVE_TOKENS[want.receive].test(t))) continue;
    if (!inTokens.some((t) => PAYMENT_TOKENS[want.payment].test(t))) continue;

    const received = leaves
      .filter((l) => /receiv|recipient|dest|payout|pay_out/i.test(l.path) && /amount|value|total|sum/i.test(l.key))
      .map((l) => numericText(l.value))
      .find((v): v is string => v !== null && Number(v) > 0);
    if (!received) continue;

    const feeLeaf = (re: RegExp) =>
      leaves.filter((l) => re.test(l.key) && !/before|list|original|gross|discount/i.test(l.path))
        .map((l) => numericText(l.value))
        .find((v): v is string => v !== null) ?? null;
    const feeBefore =
      leaves.filter((l) => /fee|tarifa|charge/i.test(l.key) && /before|list|original|gross/i.test(l.path))
        .map((l) => numericText(l.value))
        .find((v): v is string => v !== null) ?? null;
    const rate =
      leaves.filter((l) => /rate|exchange|cambio|câmbio/i.test(l.key))
        .map((l) => numericText(l.value))
        .find((v): v is string => v !== null) ?? null;
    const delivery =
      leaves.find((l) => typeof l.value === "string" && /deliver|eta|prazo|speed|time/i.test(l.key))?.value ?? null;
    // promo: text only ("100% de desconto 45.00 BRL"); a numeric field like fee_before_discount_brl is not a promo
    const promo =
      leaves.find(
        (l) =>
          typeof l.value === "string" &&
          (/promo/i.test(l.key) || (/discount|desconto/i.test(l.key) && /[a-zà-ú]{3,}/i.test(l.value))),
      )?.value ?? null;

    return {
      receive_amount_pyg: received,
      fee_brl: feeLeaf(/fee|tarifa|charge/i),
      fee_before_discount_brl: feeBefore,
      exchange_rate: rate,
      delivery: typeof delivery === "string" ? delivery : null,
      promo: typeof promo === "string" ? promo : null,
    };
  }
  return null;
}

/** Só a forma da resposta (nomes de chave e tipos, sem valores), para o diagnóstico na trilha. */
export function catalogShape(node: unknown, depth = 0): string {
  const text = shapeOf(node, depth);
  return text.length > 600 ? `${text.slice(0, 600)}…` : text;
}

function shapeOf(node: unknown, depth: number): string {
  if (depth > 7) return "…";
  if (node === null) return "null";
  if (Array.isArray(node)) return node.length === 0 ? "[0]" : `[${node.length}]<${shapeOf(node[0], depth + 1)}>`;
  if (typeof node === "object") {
    const entries = Object.entries(node).slice(0, 12);
    return `{${entries.map(([k, v]) => `${k}:${shapeOf(v, depth + 1)}`).join(",")}}`;
  }
  return typeof node;
}
