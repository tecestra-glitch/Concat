/**
 * Cruzamento de posições ("grafo de posições") — espelho TS do motor do backend (D1).
 *
 * Nó  = moeda em um local/conta (ex.: USD@banco-demo-py, PYG@chaco:CDE, BRL@brbank).
 * Aresta = uma forma de mover valor entre dois nós: uma cotação (compra/venda de uma fonte),
 *          uma transferência (mesma moeda, entre contas) ou um depósito/saque (dinheiro ↔ conta).
 *          Cada aresta carrega taxa, custos fixos/percentuais, prazo e confiança.
 *
 * Um ciclo que começa e termina no mesmo nó com valor final > inicial é uma oportunidade.
 * Com capital já estacionado em todas as contas, o ciclo pode começar em qualquer nó com saldo,
 * sem precisar mover capital antes. Como há custos fixos (que dependem do montante), avaliamos
 * cada ciclo com o montante real em vez de somar logaritmos (Bellman-Ford serve para grafos
 * grandes; aqui o grafo é pequeno e a enumeração exata até `maxLen` arestas é mais precisa).
 *
 * Dinheiro entra e sai como string decimal (D1); os números só existem dentro do cálculo.
 * `toNumber()` (de `./format`) é o único ponto de conversão para ordenar/plotar.
 */
import type { Confidence, Currency, Cycle, DataMode, Edge, Quote } from "./api/types";
import { toNumber } from "./format";

export type { Cycle, Edge };
export { toNumber };

export interface Node {
  key: string; // `${currency}@${venue}`
  currency: Currency;
  venue: string; // source id, account id or "cash:<city>"
  label: string;
}

export function nodeKey(currency: Currency, venue: string): string {
  return `${currency}@${venue}`;
}

/**
 * Número → string decimal canônica (sem notação científica, sem zeros à direita).
 * `digits` limita a fração; 12 casas bastam para ROI e taxas, 8 para montantes.
 */
export function dec(n: number, digits = 12): string {
  if (!Number.isFinite(n)) return "0";
  // `toFixed` muda para notação científica a partir de 1e21; nessa faixa o double já é inteiro.
  if (Math.abs(n) >= 1e21) return BigInt(n).toString();
  const fixed = n.toFixed(digits);
  const trimmed = fixed.includes(".") ? fixed.replace(/0+$/, "").replace(/\.$/, "") : fixed;
  return trimmed === "-0" ? "0" : trimmed;
}

const num = (v: string | number | null | undefined): number => toNumber(v) ?? 0;

/** Transforma cotações em arestas de conversão dentro da mesma fonte/conta. */
export function edgesFromQuotes(quotes: Quote[], venueOf: (q: Quote) => string): Edge[] {
  const edges: Edge[] = [];
  for (const q of quotes) {
    if (q.kind === "market_reference") continue; // referência não é executável
    const venue = venueOf(q);
    const minutes = q.modality === "cash" ? 0 : 1;
    const conf: Confidence = q.kind === "executable" ? "quoted" : "estimated";
    const pctFee = dec(q.fees.filter((f) => f.label.includes("%")).reduce((a, f) => a + num(f.amount) / 100, 0));
    const buy = toNumber(q.buy);
    if (q.buy !== null && buy !== null && buy > 0) {
      // a fonte COMPRA a moeda base: eu entrego base e recebo quote
      edges.push({ from: nodeKey(q.base, venue), to: nodeKey(q.quote, venue), kind: "quote", rate: q.buy, fee_pct: pctFee, fee_fixed: "0", minutes, via: `${q.source_id} compra ${q.base}`, confidence: conf, evidence_id: q.evidence_id });
    }
    const sell = toNumber(q.sell);
    if (sell !== null && sell > 0) {
      // a fonte VENDE a moeda base: eu entrego quote e recebo base
      edges.push({ from: nodeKey(q.quote, venue), to: nodeKey(q.base, venue), kind: "quote", rate: dec(1 / sell, 16), fee_pct: pctFee, fee_fixed: "0", minutes, via: `${q.source_id} vende ${q.base}`, confidence: conf, evidence_id: q.evidence_id });
    }
  }
  return edges;
}

/** Valor que sai da aresta para `amount` entrando: custo % sobre a entrada, custo fixo na saída. */
export function applyEdge(amount: number, e: Edge): number {
  return amount * (1 - num(e.fee_pct)) * num(e.rate) - num(e.fee_fixed);
}

const CONFIDENCE_ORDER: Confidence[] = ["quoted", "estimated", "incomplete"];

function worst(a: Confidence, b: Confidence): Confidence {
  return CONFIDENCE_ORDER[Math.max(CONFIDENCE_ORDER.indexOf(a), CONFIDENCE_ORDER.indexOf(b))];
}

export interface FindCyclesOptions {
  maxLen?: number; // 2..6, default 4
  minRoi?: string | number; // decimal string (D1) or number
  dataMode?: DataMode; // stamped on every cycle; default "demo" (this mirror only runs on demo data)
}

/**
 * Enumera ciclos simples até `maxLen` arestas a partir de cada nó de `starts`,
 * avaliando o valor com o montante informado para cada nó (saldo estacionado, string decimal).
 */
export function findCycles(edges: Edge[], starts: Record<string, string | number>, opts: FindCyclesOptions = {}): Cycle[] {
  const maxLen = opts.maxLen ?? 4;
  const minRoi = toNumber(opts.minRoi) ?? -Infinity;
  const dataMode = opts.dataMode ?? "demo";
  const out = new Map<string, Edge[]>();
  for (const e of edges) (out.get(e.from) ?? out.set(e.from, []).get(e.from)!).push(e);
  const cycles: Cycle[] = [];

  for (const [start, parked] of Object.entries(starts)) {
    const amountIn = toNumber(parked);
    if (amountIn === null || !(amountIn > 0)) continue;
    const amountInStr = typeof parked === "string" ? parked : dec(parked, 8);
    const walk = (node: string, amount: number, path: string[], used: Edge[], minutes: number, conf: Confidence) => {
      if (used.length >= maxLen) return;
      for (const e of out.get(node) ?? []) {
        if (e.to === start) {
          if (used.length === 0) continue; // precisa de pelo menos 2 arestas para ser um ciclo real
          const amountOut = applyEdge(amount, e);
          const gain = amountOut - amountIn;
          const roi = gain / amountIn;
          if (roi >= minRoi) {
            cycles.push({
              start,
              path: [...path, start],
              edges: [...used, e],
              amount_in: amountInStr,
              amount_out: dec(amountOut, 8),
              gain: dec(gain, 8),
              roi: dec(roi, 12),
              minutes: minutes + e.minutes,
              confidence: worst(conf, e.confidence),
              data_mode: dataMode,
            });
          }
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
  // Ciclos idênticos vistos de nós diferentes ficam: com saldos distintos o ROI muda.
  return cycles.sort((a, b) => num(b.roi) - num(a.roi));
}

/** Retorno em "% ao dia" para comparar ciclos com prazos diferentes (0 min → trata como 1 min). */
export function roiPerDay(c: Cycle): number {
  const minutes = Math.max(1, c.minutes);
  return num(c.roi) * (1440 / minutes);
}
