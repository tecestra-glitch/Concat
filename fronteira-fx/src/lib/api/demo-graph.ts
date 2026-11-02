/** Arestas de transferência/depósito da DEMONSTRAÇÃO (ilustrativas) + saldos estacionados por nó. */
import type { Edge } from "../graph";
import { edgesFromQuotes, nodeKey } from "../graph";
import { allDemoQuotes, demoAccounts, demoWesternUnionQuotes } from "./demo-data";
import type { Quote } from "./types";

/** venue de uma cotação na demo: fonte digital = própria fonte; casa de câmbio = fonte:cidade. */
export function demoVenue(q: Quote): string {
  return q.city ? `${q.source_id}:${q.city}` : q.source_id;
}

export function demoTransferEdges(): Edge[] {
  const wu5k = demoWesternUnionQuotes.find((q) => q.amount_base === "5000" && q.context?.receive === "bank_account")!;
  const wuCash = demoWesternUnionQuotes.find((q) => q.amount_base === "5000" && q.context?.receive === "cash_pickup")!;
  return [
    // remessa: BRL no banco BR → PYG na ueno (WU, tarifa 100 % desconto)
    { from: nodeKey("BRL", "brbank"), to: nodeKey("PYG", "ueno"), rate: Number(wu5k.sell), feePct: 0, feeFixed: 0, minutes: 2 * 1440, via: "Western Union → conta ueno (Pix)", confidence: "estimated", evidenceId: wu5k.evidence_id },
    { from: nodeKey("BRL", "brbank"), to: nodeKey("PYG", "cash:CDE"), rate: Number(wuCash.sell), feePct: 0, feeFixed: 0, minutes: 30, via: "Western Union retirada em loja (CDE)", confidence: "estimated", evidenceId: wuCash.evidence_id },
    // ueno ↔ dinheiro (saque/depósito em PYG, custo ilustrativo)
    { from: nodeKey("PYG", "ueno"), to: nodeKey("PYG", "cash:ASU"), rate: 1, feePct: 0, feeFixed: 0, minutes: 20, via: "saque ueno (ASU)", confidence: "estimated" },
    { from: nodeKey("PYG", "cash:ASU"), to: nodeKey("PYG", "ueno"), rate: 1, feePct: 0, feeFixed: 0, minutes: 20, via: "depósito ueno (ASU)", confidence: "estimated" },
    { from: nodeKey("PYG", "cash:CDE"), to: nodeKey("PYG", "ueno"), rate: 1, feePct: 0, feeFixed: 0, minutes: 30, via: "depósito ueno (CDE)", confidence: "estimated" },
    { from: nodeKey("PYG", "ueno"), to: nodeKey("PYG", "cash:CDE"), rate: 1, feePct: 0, feeFixed: 0, minutes: 30, via: "saque ueno (CDE)", confidence: "estimated" },
    // dinheiro ↔ casas de câmbio (mesma cidade, sem custo: é só caminhar até o balcão)
    ...(["chaco:CDE", "alberdi:CDE"] as const).flatMap((v) => ["PYG", "USD", "BRL"].flatMap((c) => [
      { from: nodeKey(c as "PYG", "cash:CDE"), to: nodeKey(c as "PYG", v), rate: 1, feePct: 0, feeFixed: 0, minutes: 10, via: `balcão ${v}`, confidence: "quoted" as const },
      { from: nodeKey(c as "PYG", v), to: nodeKey(c as "PYG", "cash:CDE"), rate: 1, feePct: 0, feeFixed: 0, minutes: 0, via: `balcão ${v}`, confidence: "quoted" as const },
    ])),
    ...(["chaco:ASU", "bonanza:ASU", "norte:ASU"] as const).flatMap((v) => ["PYG", "USD", "BRL"].flatMap((c) => [
      { from: nodeKey(c as "PYG", "cash:ASU"), to: nodeKey(c as "PYG", v), rate: 1, feePct: 0, feeFixed: 0, minutes: 10, via: `balcão ${v}`, confidence: "quoted" as const },
      { from: nodeKey(c as "PYG", v), to: nodeKey(c as "PYG", "cash:ASU"), rate: 1, feePct: 0, feeFixed: 0, minutes: 0, via: `balcão ${v}`, confidence: "quoted" as const },
    ])),
    // USD entre contas digitais (custo de transferência internacional ainda não confirmado → incompleto)
    { from: nodeKey("USD", "ueno"), to: nodeKey("USD", "nomad"), rate: 1, feePct: 0.003, feeFixed: 0, minutes: 1440, via: "transferência USD ueno → Nomad (custo a confirmar)", confidence: "incomplete" },
    { from: nodeKey("USD", "nomad"), to: nodeKey("USD", "ueno"), rate: 1, feePct: 0.003, feeFixed: 0, minutes: 1440, via: "transferência USD Nomad → ueno (custo a confirmar)", confidence: "incomplete" },
    // Nomad: USD → BRL (venda) de volta ao banco BR
    { from: nodeKey("USD", "nomad"), to: nodeKey("BRL", "brbank"), rate: 5.4187 * 0.9961, feePct: 0, feeFixed: 0, minutes: 1440, via: "Nomad vende USD → Pix BRL", confidence: "estimated" },
    // Brasil: cartão BR pagando em PYG (compra) não é ciclo; omitido.
  ];
}

export function demoEdges(): Edge[] {
  const quoteEdges = edgesFromQuotes(allDemoQuotes.filter((q) => q.amount_base === null && q.source_id !== "nomad"), demoVenue);
  return [...quoteEdges, ...demoTransferEdges()];
}

/** Saldos estacionados (nó → montante) a partir das contas da demo. */
export function demoParkedBalances(): Record<string, number> {
  const map: Record<string, string> = { "acc-ueno-pyg": "ueno", "acc-ueno-usd": "ueno", "acc-nomad-usd": "nomad", "acc-revolut-usd": "revolut", "acc-brl-bank": "brbank", "acc-cash-cde": "cash:CDE" };
  const out: Record<string, number> = {};
  for (const a of demoAccounts) {
    const venue = map[a.id];
    if (!venue || a.kind.startsWith("card")) continue;
    const free = Number(a.balance_free);
    if (free > 0) out[nodeKey(a.currency, venue)] = (out[nodeKey(a.currency, venue)] ?? 0) + free;
  }
  return out;
}
