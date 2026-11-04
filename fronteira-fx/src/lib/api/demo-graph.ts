/**
 * Arestas de transferência, depósito, saque e deslocamento da DEMONSTRAÇÃO (ilustrativas) + saldos
 * estacionados por nó. Tudo em string decimal (D1); só o cálculo em `../graph` converte para número.
 *
 * Trilhos e deslocamentos seguem `backend/.../data/rails.json` e `transport.json`: custo não verificado
 * vira `incomplete` e nunca zero. O ueno saiu do grafo (resolução do BCP em 03/11/2026).
 */
import { dec, edgesFromQuotes, nodeKey } from "../graph";
import { allDemoQuotes, demoAccounts, demoWesternUnionQuotes } from "./demo-data";
import type { Confidence, Currency, Edge, Quote, RouteChannel } from "./types";

/** venue de uma cotação na demo: fonte digital = própria fonte; casa de câmbio = fonte:cidade. */
export function demoVenue(q: Quote): string {
  return q.city ? `${q.source_id}:${q.city}` : q.source_id;
}

interface TransferSpec {
  kind?: Edge["kind"];
  channel: RouteChannel;
  rate?: string;
  fee_pct?: string;
  fee_fixed?: string;
  minutes: number;
  via: string;
  confidence: Confidence;
  evidence_id?: string | null;
  border?: boolean;
  counter?: boolean;
}

function transfer(from: string, to: string, spec: TransferSpec): Edge {
  return {
    from,
    to,
    kind: spec.kind ?? "transfer",
    rate: spec.rate ?? "1",
    fee_pct: spec.fee_pct ?? "0",
    fee_fixed: spec.fee_fixed ?? "0",
    minutes: spec.minutes,
    via: spec.via,
    confidence: spec.confidence,
    evidence_id: spec.evidence_id ?? null,
    channel: spec.channel,
    ...(spec.border ? { border: true } : {}),
    ...(spec.counter ? { counter: true } : {}),
  };
}

const CURRENCIES: Currency[] = ["PYG", "USD", "BRL"];

/** dinheiro ↔ balcão na mesma cidade: sem tarifa, só o deslocamento até a casa (presencial). */
function counterEdges(city: "CDE" | "ASU", venues: readonly string[]): Edge[] {
  return venues.flatMap((v) =>
    CURRENCIES.flatMap((c) => [
      transfer(nodeKey(c, `cash:${city}`), nodeKey(c, v), { channel: "presencial", minutes: 10, via: `balcão ${v}`, confidence: "quoted", counter: true }),
      transfer(nodeKey(c, v), nodeKey(c, `cash:${city}`), { channel: "presencial", minutes: 0, via: `balcão ${v}`, confidence: "quoted", counter: true }),
    ]),
  );
}

/** Ônibus entre cidades: custo ainda não verificado em `transport.json` → `incomplete` em ambos os sentidos. */
function travelEdges(a: "CDE" | "ASU", b: "CDE" | "ASU", minutes: number): Edge[] {
  return CURRENCIES.flatMap((c) => [
    transfer(nodeKey(c, `cash:${a}`), nodeKey(c, `cash:${b}`), { kind: "travel", channel: "presencial", minutes, via: `ônibus ${a} → ${b} (custo não verificado)`, confidence: "incomplete" }),
    transfer(nodeKey(c, `cash:${b}`), nodeKey(c, `cash:${a}`), { kind: "travel", channel: "presencial", minutes, via: `ônibus ${b} → ${a} (custo não verificado)`, confidence: "incomplete" }),
  ]);
}

export function demoTransferEdges(): Edge[] {
  const wu5k = demoWesternUnionQuotes.find((q) => q.amount_base === "5000" && q.context?.receive === "bank_account")!;
  const wuCash = demoWesternUnionQuotes.find((q) => q.amount_base === "5000" && q.context?.receive === "cash_pickup")!;
  return [
    // remessa: BRL no banco BR → PYG no Banco PY (WU, tarifa 100 % desconto)
    transfer(nodeKey("BRL", "brbank"), nodeKey("PYG", "banco_py"), { channel: "assistida", rate: wu5k.sell ?? "0", minutes: 2 * 1440, via: "Western Union → conta Banco PY (Pix)", confidence: "estimated", evidence_id: wu5k.evidence_id }),
    transfer(nodeKey("BRL", "brbank"), nodeKey("PYG", "cash:CDE"), { channel: "presencial", rate: wuCash.sell ?? "0", minutes: 30, via: "Western Union retirada em loja (CDE)", confidence: "estimated", evidence_id: wuCash.evidence_id }),
    // Banco PY ↔ dinheiro (saque/depósito em PYG; custo ilustrativo, não confirmado)
    transfer(nodeKey("PYG", "banco_py"), nodeKey("PYG", "cash:ASU"), { kind: "withdraw", channel: "presencial", minutes: 20, via: "saque Banco PY (ASU)", confidence: "estimated" }),
    transfer(nodeKey("PYG", "cash:ASU"), nodeKey("PYG", "banco_py"), { kind: "deposit", channel: "presencial", minutes: 20, via: "depósito Banco PY (ASU)", confidence: "estimated" }),
    transfer(nodeKey("PYG", "cash:CDE"), nodeKey("PYG", "banco_py"), { kind: "deposit", channel: "presencial", minutes: 30, via: "depósito Banco PY (CDE)", confidence: "estimated" }),
    transfer(nodeKey("PYG", "banco_py"), nodeKey("PYG", "cash:CDE"), { kind: "withdraw", channel: "presencial", minutes: 30, via: "saque Banco PY (CDE)", confidence: "estimated" }),
    // dinheiro ↔ casas de câmbio (mesma cidade)
    ...counterEdges("CDE", ["chaco:CDE", "alberdi:CDE"]),
    ...counterEdges("ASU", ["chaco:ASU", "bonanza:ASU", "norte:ASU"]),
    // Pix BR ↔ Revolut (BRL) e conversão BR → Nomad (USD): trilhos sem custo validado → incompleto
    transfer(nodeKey("BRL", "brbank"), nodeKey("BRL", "revolut"), { channel: "assistida", minutes: 5, via: "Pix → Revolut BRL (custo não verificado)", confidence: "incomplete", border: true }),
    transfer(nodeKey("BRL", "revolut"), nodeKey("BRL", "brbank"), { channel: "assistida", minutes: 5, via: "Pix Revolut BRL → banco BR (custo não verificado)", confidence: "incomplete", border: true }),
    transfer(nodeKey("BRL", "brbank"), nodeKey("USD", "nomad"), { channel: "assistida", rate: dec(1 / 5.4043, 12), minutes: 1440, via: "conversão BRL → Nomad USD (custo não verificado)", confidence: "incomplete" }),
    // USD entre contas digitais (transferência internacional sem custo confirmado → incompleto)
    transfer(nodeKey("USD", "revolut"), nodeKey("USD", "nomad"), { channel: "assistida", fee_pct: "0.003", minutes: 60, via: "transferência USD Revolut → Nomad (custo a confirmar)", confidence: "incomplete" }),
    transfer(nodeKey("USD", "nomad"), nodeKey("USD", "revolut"), { channel: "assistida", fee_pct: "0.003", minutes: 60, via: "transferência USD Nomad → Revolut (custo a confirmar)", confidence: "incomplete" }),
    // Nomad: USD → BRL (venda) de volta ao banco BR (cotação pública líquida de spread)
    transfer(nodeKey("USD", "nomad"), nodeKey("BRL", "brbank"), { channel: "assistida", rate: dec(5.431 * 0.9961, 8), minutes: 1440, via: "Nomad vende USD → Pix BRL", confidence: "estimated" }),
    // deslocamento entre cidades (ônibus), sem custo verificado
    ...travelEdges("CDE", "ASU", 240),
    // Brasil: cartão BR pagando em PYG (compra) não é ciclo; omitido.
  ];
}

export function demoEdges(): Edge[] {
  const quoteEdges = edgesFromQuotes(allDemoQuotes.filter((q) => q.amount_base === null && q.source_id !== "nomad"), demoVenue);
  return [...quoteEdges, ...demoTransferEdges()];
}

const ACCOUNT_VENUE: Record<string, string> = {
  "acc-banco-py-pyg": "banco_py",
  "acc-nomad-usd": "nomad",
  "acc-revolut-usd": "revolut",
  "acc-revolut-brl": "revolut",
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
