/**
 * Arestas de transferência/depósito da DEMONSTRAÇÃO (ilustrativas) + saldos estacionados por nó.
 * Tudo em string decimal (D1); só o cálculo em `../graph` converte para número.
 */
import { dec, edgesFromQuotes, nodeKey } from "../graph";
import { allDemoQuotes, demoAccounts, demoWesternUnionQuotes } from "./demo-data";
import type { Confidence, Currency, Edge, Quote } from "./types";

/** venue de uma cotação na demo: fonte digital = própria fonte; casa de câmbio = fonte:cidade. */
export function demoVenue(q: Quote): string {
  return q.city ? `${q.source_id}:${q.city}` : q.source_id;
}

interface TransferSpec {
  rate?: string;
  fee_pct?: string;
  fee_fixed?: string;
  minutes: number;
  via: string;
  confidence: Confidence;
  evidence_id?: string | null;
}

function transfer(from: string, to: string, spec: TransferSpec): Edge {
  return {
    from,
    to,
    kind: "transfer",
    rate: spec.rate ?? "1",
    fee_pct: spec.fee_pct ?? "0",
    fee_fixed: spec.fee_fixed ?? "0",
    minutes: spec.minutes,
    via: spec.via,
    confidence: spec.confidence,
    evidence_id: spec.evidence_id ?? null,
  };
}

const CURRENCIES: Currency[] = ["PYG", "USD", "BRL"];

/** dinheiro ↔ balcão na mesma cidade: sem custo, só o deslocamento até a casa. */
function counterEdges(city: "CDE" | "ASU", venues: readonly string[]): Edge[] {
  return venues.flatMap((v) =>
    CURRENCIES.flatMap((c) => [
      transfer(nodeKey(c, `cash:${city}`), nodeKey(c, v), { minutes: 10, via: `balcão ${v}`, confidence: "quoted" }),
      transfer(nodeKey(c, v), nodeKey(c, `cash:${city}`), { minutes: 0, via: `balcão ${v}`, confidence: "quoted" }),
    ]),
  );
}

export function demoTransferEdges(): Edge[] {
  const wu5k = demoWesternUnionQuotes.find((q) => q.amount_base === "5000" && q.context?.receive === "bank_account")!;
  const wuCash = demoWesternUnionQuotes.find((q) => q.amount_base === "5000" && q.context?.receive === "cash_pickup")!;
  return [
    // remessa: BRL no banco BR → PYG na banco demo PY (WU, tarifa 100 % desconto)
    transfer(nodeKey("BRL", "brbank"), nodeKey("PYG", "banco-demo-py"), { rate: wu5k.sell ?? "0", minutes: 2 * 1440, via: "Western Union → conta banco demo PY (Pix)", confidence: "estimated", evidence_id: wu5k.evidence_id }),
    transfer(nodeKey("BRL", "brbank"), nodeKey("PYG", "cash:CDE"), { rate: wuCash.sell ?? "0", minutes: 30, via: "Western Union retirada em loja (CDE)", confidence: "estimated", evidence_id: wuCash.evidence_id }),
    // banco demo PY ↔ dinheiro (saque/depósito em PYG, custo ilustrativo)
    transfer(nodeKey("PYG", "banco-demo-py"), nodeKey("PYG", "cash:ASU"), { minutes: 20, via: "saque banco demo PY (ASU)", confidence: "estimated" }),
    transfer(nodeKey("PYG", "cash:ASU"), nodeKey("PYG", "banco-demo-py"), { minutes: 20, via: "depósito banco demo PY (ASU)", confidence: "estimated" }),
    transfer(nodeKey("PYG", "cash:CDE"), nodeKey("PYG", "banco-demo-py"), { minutes: 30, via: "depósito banco demo PY (CDE)", confidence: "estimated" }),
    transfer(nodeKey("PYG", "banco-demo-py"), nodeKey("PYG", "cash:CDE"), { minutes: 30, via: "saque banco demo PY (CDE)", confidence: "estimated" }),
    // dinheiro ↔ casas de câmbio (mesma cidade)
    ...counterEdges("CDE", ["chaco:CDE", "alberdi:CDE"]),
    ...counterEdges("ASU", ["chaco:ASU", "bonanza:ASU", "norte:ASU"]),
    // USD entre contas digitais (custo de transferência internacional ainda não confirmado → incompleto)
    transfer(nodeKey("USD", "banco-demo-py"), nodeKey("USD", "nomad"), { fee_pct: "0.003", minutes: 1440, via: "transferência USD banco demo PY → Nomad (custo a confirmar)", confidence: "incomplete" }),
    transfer(nodeKey("USD", "nomad"), nodeKey("USD", "banco-demo-py"), { fee_pct: "0.003", minutes: 1440, via: "transferência USD Nomad → banco demo PY (custo a confirmar)", confidence: "incomplete" }),
    // Nomad: USD → BRL (venda) de volta ao banco BR (cotação pública líquida de spread)
    transfer(nodeKey("USD", "nomad"), nodeKey("BRL", "brbank"), { rate: dec(5.431 * 0.9961, 8), minutes: 1440, via: "Nomad vende USD → Pix BRL", confidence: "estimated" }),
    // Brasil: cartão BR pagando em PYG (compra) não é ciclo; omitido.
  ];
}

export function demoEdges(): Edge[] {
  const quoteEdges = edgesFromQuotes(allDemoQuotes.filter((q) => q.amount_base === null && q.source_id !== "nomad"), demoVenue);
  return [...quoteEdges, ...demoTransferEdges()];
}

const ACCOUNT_VENUE: Record<string, string> = {
  "acc-banco-demo-py-pyg": "banco-demo-py",
  "acc-banco-demo-py-usd": "banco-demo-py",
  "acc-nomad-usd": "nomad",
  "acc-revolut-usd": "revolut",
  "acc-brl-bank": "brbank",
  "acc-cash-cde": "cash:CDE",
};

/** Saldos estacionados (nó → montante em string decimal) a partir das contas da demo. */
export function demoParkedBalances(): Record<string, string> {
  const sums = new Map<string, number>();
  for (const a of demoAccounts) {
    const venue = ACCOUNT_VENUE[a.id];
    if (!venue || a.kind.startsWith("card")) continue;
    const free = Number(a.balance_free);
    if (!(free > 0)) continue;
    const key = nodeKey(a.currency, venue);
    sums.set(key, (sums.get(key) ?? 0) + free);
  }
  const out: Record<string, string> = {};
  for (const [key, total] of sums) out[key] = dec(total, 8);
  return out;
}
