/**
 * Cruzamento de posições ("grafo de posições").
 *
 * Nó  = moeda em um local/conta (ex.: USD@ueno, PYG@chaco:CDE, BRL@brbank).
 * Aresta = uma forma de mover valor entre dois nós: uma cotação (compra/venda de uma fonte),
 *          uma transferência (mesma moeda, entre contas) ou um depósito/saque (dinheiro ↔ conta).
 *          Cada aresta carrega taxa, custos fixos/percentuais, prazo e confiança.
 *
 * Um ciclo que começa e termina no mesmo nó com valor final > inicial é uma oportunidade.
 * Com capital já estacionado em todas as contas, o ciclo pode começar em qualquer nó com saldo,
 * sem precisar mover capital antes. Como há custos fixos (que dependem do montante), avaliamos
 * cada ciclo com o montante real em vez de somar logaritmos (Bellman-Ford serve para grafos
 * grandes; aqui o grafo é pequeno e a enumeração exata até 4 arestas é mais precisa).
 */
import type { Confidence, Currency, Quote } from "./api/types";

export interface Node {
  key: string; // `${currency}@${venue}`
  currency: Currency;
  venue: string; // source id, account id or "cash:<city>"
  label: string;
}

export interface Edge {
  from: string;
  to: string;
  rate: number; // unidades de `to` por 1 unidade de `from`, antes de custos
  feePct: number; // custo proporcional (0.01 = 1 %) cobrado sobre a entrada
  feeFixed: number; // custo fixo na moeda de SAÍDA
  minutes: number; // prazo estimado em minutos
  via: string; // descrição (fonte / meio)
  confidence: Confidence;
  evidenceId?: string | null;
}

export interface Cycle {
  start: string;
  path: string[]; // nós visitados, começa e termina em start
  edges: Edge[];
  amountIn: number;
  amountOut: number;
  gain: number;
  roi: number;
  minutes: number;
  confidence: Confidence;
}

export function nodeKey(currency: Currency, venue: string): string {
  return `${currency}@${venue}`;
}

/** Transforma cotações em arestas de conversão dentro da mesma fonte/conta. */
export function edgesFromQuotes(quotes: Quote[], venueOf: (q: Quote) => string): Edge[] {
  const edges: Edge[] = [];
  for (const q of quotes) {
    if (q.kind === "market_reference") continue; // referência não é executável
    const venue = venueOf(q);
    const minutes = q.modality === "cash" ? 0 : 1;
    const conf: Confidence = q.kind === "executable" ? "quoted" : "estimated";
    const pctFee = q.fees.filter((f) => f.label.includes("%")).reduce((a, f) => a + Number(f.amount) / 100, 0);
    if (q.buy !== null && Number(q.buy) > 0) {
      // a fonte COMPRA a moeda base: eu entrego base e recebo quote
      edges.push({ from: nodeKey(q.base, venue), to: nodeKey(q.quote, venue), rate: Number(q.buy), feePct: pctFee, feeFixed: 0, minutes, via: `${q.source_id} compra ${q.base}`, confidence: conf, evidenceId: q.evidence_id });
    }
    if (q.sell !== null && Number(q.sell) > 0) {
      // a fonte VENDE a moeda base: eu entrego quote e recebo base
      edges.push({ from: nodeKey(q.quote, venue), to: nodeKey(q.base, venue), rate: 1 / Number(q.sell), feePct: pctFee, feeFixed: 0, minutes, via: `${q.source_id} vende ${q.base}`, confidence: conf, evidenceId: q.evidence_id });
    }
  }
  return edges;
}

export function applyEdge(amount: number, e: Edge): number {
  return amount * (1 - e.feePct) * e.rate - e.feeFixed;
}

function worst(a: Confidence, b: Confidence): Confidence {
  const order: Confidence[] = ["quoted", "estimated", "incomplete"];
  return order[Math.max(order.indexOf(a), order.indexOf(b))];
}

/**
 * Enumera ciclos simples até `maxLen` arestas a partir de cada nó de `starts`,
 * avaliando o valor com o montante informado para cada nó (saldo estacionado).
 */
export function findCycles(edges: Edge[], starts: Record<string, number>, opts: { maxLen?: number; minRoi?: number } = {}): Cycle[] {
  const maxLen = opts.maxLen ?? 4;
  const minRoi = opts.minRoi ?? -Infinity;
  const out = new Map<string, Edge[]>();
  for (const e of edges) (out.get(e.from) ?? out.set(e.from, []).get(e.from)!).push(e);
  const cycles: Cycle[] = [];

  for (const [start, amountIn] of Object.entries(starts)) {
    if (!(amountIn > 0)) continue;
    const walk = (node: string, amount: number, path: string[], used: Edge[], minutes: number, conf: Confidence) => {
      if (used.length >= maxLen) return;
      for (const e of out.get(node) ?? []) {
        if (e.to === start) {
          if (used.length === 0) continue; // precisa de pelo menos 2 arestas para ser um ciclo real
          const amountOut = applyEdge(amount, e);
          const gain = amountOut - amountIn;
          const roi = gain / amountIn;
          if (roi >= minRoi) cycles.push({ start, path: [...path, start], edges: [...used, e], amountIn, amountOut, gain, roi, minutes: minutes + e.minutes, confidence: worst(conf, e.confidence) });
          continue;
        }
        if (path.includes(e.to)) continue; // ciclo simples: não repete nós
        const next = applyEdge(amount, e);
        if (next <= 0) continue;
        walk(e.to, next, [...path, e.to], [...used, e], minutes + e.minutes, worst(conf, e.confidence));
      }
    };
    walk(start, amountIn, [start], [], 0, "quoted");
  }
  // remove ciclos idênticos vistos de nós diferentes? Não: com saldos distintos o ROI muda; mantemos todos.
  return cycles.sort((a, b) => b.roi - a.roi);
}

/** Retorno em "% ao dia" para comparar ciclos com prazos diferentes (0 min → trata como 1 min). */
export function roiPerDay(c: Cycle): number {
  const minutes = Math.max(1, c.minutes);
  return c.roi * (1440 / minutes);
}
