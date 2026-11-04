/**
 * Cruzamento de posições ("grafo de posições") — espelho TS do motor do backend (D1).
 *
 * Nó  = moeda em um local/conta (ex.: USD@revolut, PYG@chaco:CDE, BRL@brbank, PYG@cash:ASU).
 * Aresta = uma forma de mover valor entre dois nós: uma cotação (compra/venda de uma fonte),
 *          uma transferência (entre contas e lugares digitais), um depósito/saque (dinheiro ↔ conta)
 *          ou um deslocamento entre cidades (kind `travel`). Cada aresta carrega taxa, custos, prazo,
 *          confiança e canal (presencial | assistida | automatizavel).
 *
 * Um ciclo que começa e termina no mesmo nó com valor final > inicial é uma oportunidade. Cada ciclo
 * vira `legs[]` (uma perna por aresta) com custos na moeda de origem da perna; os custos do ciclo são
 * somados na moeda de partida, e `null` quando algum custo daquela categoria é desconhecido.
 *
 * Dinheiro entra e sai como string decimal (D1); os números só existem dentro do cálculo.
 * `toNumber()` (de `./format`) é o único ponto de conversão para ordenar/plotar.
 */
import type { Confidence, Currency, Cycle, DataMode, Edge, GainByCurrency, Leg, LegKind, LegCosts, Quote, RouteChannel } from "./api/types";
import { toNumber } from "./format";

export type { Cycle, Edge, Leg };
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

/**
 * Taxas de valoração da DEMONSTRAÇÃO (referência BCP de 2026-10-30), em guaranis por 1 unidade.
 * Conversões entre quaisquer duas moedas passam pelo PYG. O motor real usa as cotações do dia.
 */
export const DEMO_PYG_PER_UNIT: Record<Currency, number> = { PYG: 1, BRL: 1099.99, USD: 5944.76 };

/** Converte `amount` de uma moeda para outra pelas taxas de valoração (pivô PYG). */
export function convertValue(amount: number, from: Currency, to: Currency, rates: Record<Currency, number> = DEMO_PYG_PER_UNIT): number {
  return (amount * rates[from]) / rates[to];
}

/** Limite de declaração: perna de fronteira acima de US$ 10 000 (aviso, não bloqueio). */
export const DECLARATION_USD = 10_000;

/** Transforma cotações em arestas de conversão dentro da mesma fonte/conta. */
export function edgesFromQuotes(quotes: Quote[], venueOf: (q: Quote) => string): Edge[] {
  const edges: Edge[] = [];
  for (const q of quotes) {
    if (q.kind === "market_reference") continue; // referência não é executável
    const venue = venueOf(q);
    const minutes = q.modality === "cash" ? 0 : 1;
    const conf: Confidence = q.kind === "executable" ? "quoted" : "estimated";
    const channel: RouteChannel = q.modality === "cash" ? "presencial" : "assistida";
    const pctFee = dec(q.fees.filter((f) => f.label.includes("%")).reduce((a, f) => a + num(f.amount) / 100, 0));
    const buy = toNumber(q.buy);
    const sell = toNumber(q.sell);
    const mid = buy !== null && sell !== null && buy > 0 && sell > 0 ? (buy + sell) / 2 : null;
    if (q.buy !== null && buy !== null && buy > 0) {
      // a fonte COMPRA a moeda base: eu entrego base e recebo quote
      const iof = iofApplies(venue, q.base, q.quote); // BRL que sai do Brasil: IOF desconhecido
      edges.push({ from: nodeKey(q.base, venue), to: nodeKey(q.quote, venue), kind: "quote", rate: q.buy, fee_pct: pctFee, fee_fixed: "0", minutes, via: `${q.source_id} compra ${q.base}`, confidence: iof ? "incomplete" : conf, evidence_id: q.evidence_id, channel, ref_rate: mid === null ? null : dec(mid, 12) });
    }
    if (sell !== null && sell > 0) {
      // a fonte VENDE a moeda base: eu entrego quote e recebo base
      const iof = iofApplies(venue, q.quote, q.base);
      edges.push({ from: nodeKey(q.quote, venue), to: nodeKey(q.base, venue), kind: "quote", rate: dec(1 / sell, 16), fee_pct: pctFee, fee_fixed: "0", minutes, via: `${q.source_id} vende ${q.base}`, confidence: iof ? "incomplete" : conf, evidence_id: q.evidence_id, channel, ref_rate: mid === null ? null : dec(1 / mid, 16) });
    }
  }
  return edges;
}

/** Valor que sai da aresta para `amount` entrando (contrato): `x * (1 - fee_pct - iof_pct) * rate - fee_fixed - transport_fixed`. */
export function applyEdge(amount: number, e: Edge): number {
  return amount * (1 - num(e.fee_pct) - num(e.iof_pct)) * num(e.rate) - num(e.fee_fixed) - num(e.transport_fixed);
}

const BR_INSTITUTIONS = new Set(["brbank", "nubank", "itau", "bradesco", "caixa", "revolut", "nomad"]);

/**
 * IOF de câmbio incide quando BRL é convertido por instituição brasileira (ou casa de FOZ/PPO). A alíquota não está
 * nos trilhos: sem ela, o IOF é desconhecido (`null`) e a aresta é `incomplete`, como no backend.
 */
export function iofApplies(venue: string, from: Currency, to: Currency): boolean {
  if (from !== "BRL" || to === "BRL") return false;
  const [head, city] = venue.split(":");
  if (head === "cash") return false;
  if (city !== undefined) return city === "FOZ" || city === "PPO";
  return BR_INSTITUTIONS.has(head);
}

const CONFIDENCE_ORDER: Confidence[] = ["quoted", "estimated", "incomplete"];

function worst(a: Confidence, b: Confidence): Confidence {
  return CONFIDENCE_ORDER[Math.max(CONFIDENCE_ORDER.indexOf(a), CONFIDENCE_ORDER.indexOf(b))];
}

const LEG_KIND: Record<Edge["kind"], LegKind> = { quote: "exchange", transfer: "transfer", deposit: "deposit", withdraw: "withdraw", travel: "travel" };
const currencyOf = (node: string) => node.split("@")[0] as Currency;
const venueOf = (node: string) => node.slice(node.indexOf("@") + 1);

/**
 * Custos de UMA perna, na moeda em que ela começou. Desconhecido = `null` (nunca zero):
 * aresta `incomplete` não tem custo confirmado; trilho BRL por banco brasileiro com conversão tem IOF não calculado;
 * deslocamento sem custo validado tem transporte desconhecido.
 */
function legCosts(e: Edge, amountIn: number): LegCosts {
  const currency = currencyOf(e.from);
  const unknown = e.confidence === "incomplete";
  const rate = num(e.rate);
  const converts = currencyOf(e.from) !== currencyOf(e.to);
  let spread: string | null = "0";
  if (e.kind === "quote") {
    if (!unknown && e.ref_rate && num(e.ref_rate) > 0) spread = dec(amountIn * (1 - rate / num(e.ref_rate)), 8);
    else spread = null;
  } else if (converts) {
    spread = null; // conversão por transferência sem taxa de referência: spread desconhecido, nunca zero
  }
  const fees = unknown ? null : dec(amountIn * num(e.fee_pct) + (rate > 0 ? num(e.fee_fixed) / rate : 0), 8);
  const iof = iofApplies(venueOf(e.from), currency, currencyOf(e.to)) ? null : "0";
  const transport = e.kind === "travel" ? (unknown ? null : dec(num(e.transport_fixed), 8)) : "0";
  return { currency, spread, fees, iof, transport };
}

export interface FindCyclesOptions {
  maxLen?: number; // 2..6, default 4
  minRoi?: string | number; // decimal string (D1) or number
  dataMode?: DataMode; // stamped on every cycle; default "demo" (this mirror only runs on demo data)
}

/** Pernas, custos somados na moeda de partida, ganho por moeda e aviso de declaração de um ciclo já avaliado. */
function describeCycle(start: string, edges: Edge[], amountIn: number): Pick<Cycle, "legs" | "costs" | "gain_by_currency" | "requires_declaration"> & { gain: number; amountOut: number } {
  const startCurrency = currencyOf(start);
  const legs: Leg[] = [];
  const sums: Record<"spread" | "fees" | "iof" | "transport", number | null> = { spread: 0, fees: 0, iof: 0, transport: 0 };
  let cur = amountIn;
  let requiresDeclaration = false;
  for (const e of edges) {
    const legIn = cur;
    const legOut = applyEdge(cur, e);
    const costs = legCosts(e, legIn);
    // proporção: unidades da moeda da perna que correspondem a 1 unidade do capital neste ciclo
    const perStart = legIn / amountIn;
    for (const k of ["spread", "fees", "iof", "transport"] as const) {
      const v = costs[k];
      if (sums[k] === null) continue;
      if (v === null) sums[k] = null;
      else sums[k] = (sums[k] as number) + num(v) / perStart;
    }
    const border = e.border === true;
    if (border && convertValue(legIn, costs.currency, "USD") > DECLARATION_USD) requiresDeclaration = true;
    legs.push({
      kind: LEG_KIND[e.kind],
      channel: e.channel,
      from: e.from,
      to: e.to,
      via: e.via,
      minutes: e.minutes,
      border,
      amount_in: dec(legIn, 8),
      amount_out: dec(legOut, 8),
      costs,
    });
    cur = legOut;
  }
  const gain = cur - amountIn;
  const gainByCurrency = {} as GainByCurrency;
  for (const c of ["BRL", "USD", "PYG"] as const) gainByCurrency[c] = dec(convertValue(gain, startCurrency, c), 8);
  const costs = Object.fromEntries(
    (["spread", "fees", "iof", "transport"] as const).map((k) => [k, sums[k] === null ? null : dec(sums[k] as number, 8)]),
  ) as unknown as Cycle["costs"];
  return { legs, costs, gain_by_currency: gainByCurrency, requires_declaration: requiresDeclaration, gain, amountOut: cur };
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
    // profundidade em pernas: balcão (counter) não conta, como no backend
    const walk = (node: string, amount: number, path: string[], used: Edge[], legs: number, minutes: number, conf: Confidence) => {
      for (const e of out.get(node) ?? []) {
        const step = e.counter ? 0 : 1;
        if (legs + step > maxLen) continue;
        if (e.to === start) {
          if (used.length === 0) continue; // precisa de pelo menos 2 arestas para ser um ciclo real
          const amountOut = applyEdge(amount, e);
          const gain = amountOut - amountIn;
          const roi = gain / amountIn;
          if (roi >= minRoi) {
            const edgesOfCycle = [...used, e];
            const described = describeCycle(start, edgesOfCycle, amountIn);
            cycles.push({
              start,
              path: [...path, start],
              edges: edgesOfCycle,
              legs: described.legs,
              amount_in: amountInStr,
              amount_out: dec(amountOut, 8),
              gain: dec(gain, 8),
              roi: dec(roi, 12),
              gain_by_currency: described.gain_by_currency,
              costs: described.costs,
              requires_declaration: described.requires_declaration,
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
        walk(e.to, next, [...path, e.to], [...used, e], legs + step, minutes + e.minutes, worst(conf, e.confidence));
      }
    };
    walk(start, amountIn, [start], [], 0, 0, "quoted");
  }
  // Ciclos idênticos vistos de nós diferentes ficam: com saldos distintos o ROI muda.
  return cycles.sort((a, b) => num(b.roi) - num(a.roi));
}

/** Retorno em "% ao dia" para comparar ciclos com prazos diferentes (0 min → trata como 1 min). */
export function roiPerDay(c: Cycle): number {
  const minutes = Math.max(1, c.minutes);
  return num(c.roi) * (1440 / minutes);
}

export type { Currency, LegCosts, LegKind, RouteChannel };
