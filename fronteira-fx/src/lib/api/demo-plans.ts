/**
 * Planos de execução da DEMONSTRAÇÃO. Mesmas regras do backend (`services/plans.py`), mas em memória e
 * sem nenhuma chamada de banco, corretora ou banco: nada aqui movimenta dinheiro.
 */
import type { Cycle, Leg, Plan, PlanStep, StepDone } from "./types";
import { ApiError } from "./errors";
import { applyPlanClock, canApprove, canCompleteStep, canReject, nextPendingStep } from "../plans";
import { formatMoney, toNumber } from "../format";
import { demoSources } from "./demo-data";

const plans = new Map<string, Plan>();
let counter = 0;
export const DEMO_QUOTE_MAX_AGE_S = 900;

/** Test helper: zera os planos da demonstração. */
export function resetDemoPlans(): void {
  plans.clear();
  counter = 0;
}

const currencyOf = (node: string) => node.split("@")[0] as Plan["currency"];
const venueOf = (node: string) => node.slice(node.indexOf("@") + 1);

/** Nome em português simples de um lugar do grafo: "chaco:CDE" → "Cambios Chaco (CDE)", "cash:CDE" → "dinheiro em CDE". */
export function venueName(node: string): string {
  const venue = venueOf(node);
  const [head, city] = venue.split(":");
  if (head === "cash") return `dinheiro em ${city}`;
  const name = demoSources.find((s) => s.id === head)?.name ?? DEMO_VENUE_NAMES[head] ?? head;
  return city ? `${name} (${city})` : name;
}

// mesmos nomes do backend (services/plans.py INSTITUTION_NAMES)
const DEMO_VENUE_NAMES: Record<string, string> = { "banco-demo-py": "banco paraguaio", brbank: "banco brasileiro", revolut: "Revolut", nomad: "Nomad", nubank: "Nubank", itau: "Itaú", bradesco: "Bradesco", caixa: "Caixa" };

/** Valor no texto do passo: PYG sem centavos; BRL e USD com centavos só quando há. */
export function plainAmount(value: string, currency: Plan["currency"]): string {
  const n = toNumber(value) ?? 0;
  return `${n.toLocaleString("pt-BR", { minimumFractionDigits: 0, maximumFractionDigits: currency === "PYG" ? 0 : 2 })} ${currency}`;
}

/** Força relativa para a convenção do balcão (mesma ordem do backend: USD > BRL > PYG). */
const CURRENCY_STRENGTH: Record<Plan["currency"], number> = { USD: 3, BRL: 2, PYG: 1 };

/** Cotação na convenção do balcão: "1 USD = 5,40 BRL", "1 BRL = 1.300 PYG". Nunca arredonda o preço para zero. */
export function rateText(amountIn: string, amountOut: string, fromC: Plan["currency"], toC: Plan["currency"]): string {
  const a = toNumber(amountIn) ?? 0;
  const b = toNumber(amountOut) ?? 0;
  if (!(a > 0) || !(b > 0)) return "cotação não informada";
  const fromStronger = CURRENCY_STRENGTH[fromC] > CURRENCY_STRENGTH[toC];
  const strong = fromStronger ? fromC : toC;
  const weak = fromStronger ? toC : fromC;
  const perStrong = fromStronger ? b / a : a / b;
  const places = weak === "PYG" ? 0 : 2;
  const body = perStrong.toLocaleString("pt-BR", { minimumFractionDigits: places, maximumFractionDigits: places });
  return `1 ${strong} = ${body} ${weak}`;
}

/** Texto pt-BR de uma perna (um passo do plano), com as mesmas frases do backend. */
export function legStepText(leg: Leg): string {
  const fromC = currencyOf(leg.from);
  const toC = currencyOf(leg.to);
  switch (leg.kind) {
    case "exchange":
      return `Compre ${plainAmount(leg.amount_out, toC)} na ${venueName(leg.from)} pagando ${plainAmount(leg.amount_in, fromC)} (cotação: ${rateText(leg.amount_in, leg.amount_out, fromC, toC)})`;
    case "transfer":
      if (fromC !== toC) {
        return `Envie ${plainAmount(leg.amount_in, fromC)} de ${venueName(leg.from)} e receba ≈ ${plainAmount(leg.amount_out, toC)} em ${venueName(leg.to)} (≈ ${leg.minutes} min)`;
      }
      return `Transfira ${plainAmount(leg.amount_in, fromC)} de ${venueName(leg.from)} para ${venueName(leg.to)} (≈ ${leg.minutes} min)`;
    case "deposit":
      return `Deposite ${plainAmount(leg.amount_in, fromC)} em ${venueName(leg.to)}`;
    case "withdraw":
      return `Saque ${plainAmount(leg.amount_in, fromC)} de ${venueName(leg.from)}`;
    case "travel":
      return `Leve o dinheiro de ${venueOf(leg.from).split(":")[1] ?? venueOf(leg.from)} para ${venueOf(leg.to).split(":")[1] ?? venueOf(leg.to)} (≈ ${leg.minutes} min)`;
  }
}

/** Plano proposto a partir de um ciclo atual: um passo por perna, todos pendentes. */
export function createDemoPlan(cycle: Cycle, now: number): Plan {
  // mesma regra do backend: um plano só organiza uma rota com ganho líquido positivo
  if (!((toNumber(cycle.gain) ?? 0) > 0)) throw new ApiError(422, "só ciclo com ganho líquido positivo vira plano");
  // validade pela cotação mais velha do ciclo (mesma regra do backend); sem data, não há como provar: não cria
  const quotedMs = cycle.edges.map((e) => (e.quoted_at ? Date.parse(e.quoted_at) : NaN)).filter(Number.isFinite);
  if (quotedMs.length === 0) throw new ApiError(422, "ciclo sem data de cotação; calcule os ciclos de novo");
  const id = `demo-plan-${++counter}`;
  const iso = new Date(now).toISOString();
  const steps: PlanStep[] = cycle.legs.map((leg, i) => ({
    n: i + 1,
    kind: leg.kind,
    channel: leg.channel,
    text: legStepText(leg),
    from: leg.from,
    to: leg.to,
    amount_in: leg.amount_in,
    amount_out_expected: leg.amount_out,
    minutes: leg.minutes,
    status: "pending",
    actual_out: null,
    note: null,
    done_at: null,
  }));
  const plan: Plan = {
    id,
    status: "proposed",
    start: cycle.start,
    path: cycle.path,
    currency: currencyOf(cycle.start),
    amount_in: cycle.amount_in,
    amount_out_expected: cycle.amount_out,
    gain_expected: cycle.gain,
    gain_by_currency: cycle.gain_by_currency,
    costs: cycle.costs ?? null,
    confidence: cycle.confidence,
    minutes: cycle.minutes,
    requires_declaration: cycle.requires_declaration,
    quotes_as_of: new Date(Math.min(...quotedMs)).toISOString(),
    quote_max_age_s: DEMO_QUOTE_MAX_AGE_S,
    created_at: iso,
    decided_at: null,
    completed_at: null,
    data_mode: "demo",
    steps,
  };
  plans.set(id, plan);
  return structuredClone(plan);
}

function stored(id: string): Plan {
  const p = plans.get(id);
  if (!p) throw new ApiError(404, `plano ${id} não encontrado (demonstração)`);
  return p;
}

/** Lê com o relógio aplicado (expira quem passou de 900 s antes do primeiro passo). */
export function getDemoPlan(id: string, now: number): Plan {
  const p = stored(id);
  const clocked = applyPlanClock(p, now);
  if (clocked.status !== p.status) plans.set(id, { ...p, status: clocked.status });
  return structuredClone(plans.get(id)!);
}

/** Mais recentes primeiro. */
export function listDemoPlans(now: number): Plan[] {
  return [...plans.keys()].reverse().map((id) => getDemoPlan(id, now));
}

function refuse(plan: Plan, now: number, action: string): never {
  const clocked = applyPlanClock(plan, now);
  if (clocked.status === "expired") throw new ApiError(409, `plano expirado: a cotação mais velha passou de ${DEMO_QUOTE_MAX_AGE_S} s; gere um novo plano`);
  throw new ApiError(409, `não é possível ${action} um plano em status ${clocked.status}`);
}

export function approveDemoPlan(id: string, now: number): Plan {
  const p = getDemoPlan(id, now);
  if (!canApprove(p, now)) refuse(p, now, "aprovar");
  plans.set(id, { ...p, status: "approved", decided_at: new Date(now).toISOString() });
  return getDemoPlan(id, now);
}

export function rejectDemoPlan(id: string, now: number): Plan {
  const p = getDemoPlan(id, now);
  if (!canReject(p, now)) refuse(p, now, "recusar");
  plans.set(id, { ...p, status: "rejected", decided_at: new Date(now).toISOString() });
  return getDemoPlan(id, now);
}

/** Resultado do passo: `journal` só vem preenchido quando o último passo conclui o plano. */
export function completeDemoStep(id: string, n: number, body: StepDone, now: number): { plan: Plan; journal: { text: string; expected: string; realized: string; currency: Plan["currency"] } | null } {
  const p = getDemoPlan(id, now);
  const step = p.steps.find((s) => s.n === n);
  if (!step) throw new ApiError(404, `passo ${n} não existe no plano ${id}`);
  if (!/^\d+(\.\d+)?$/.test(body.actual_out)) throw new ApiError(422, "actual_out deve ser um decimal em string (ex.: \"5090\")");
  if (step.status === "done") throw new ApiError(409, `o passo ${n} já foi feito`);
  if (!canCompleteStep(p, n, now)) {
    const clocked = applyPlanClock(p, now);
    if (clocked.status === "expired") refuse(p, now, "concluir passo de");
    if (clocked.status !== "approved" && clocked.status !== "in_progress") throw new ApiError(409, `o plano precisa estar aprovado para concluir passos (status ${clocked.status})`);
    throw new ApiError(409, `passos em ordem: o próximo é o passo ${nextPendingStep(p)?.n ?? n}`);
  }
  const iso = new Date(now).toISOString();
  const steps = p.steps.map((s) => (s.n === n ? { ...s, status: "done" as const, actual_out: body.actual_out, note: body.note ?? null, done_at: iso } : s));
  const allDone = steps.every((s) => s.status === "done");
  const updated: Plan = { ...p, steps, status: allDone ? "done" : "in_progress", completed_at: allDone ? iso : null };
  plans.set(id, updated);
  if (!allDone) return { plan: getDemoPlan(id, now), journal: null };
  const expected = updated.amount_out_expected;
  const realized = steps[steps.length - 1].actual_out!;
  const diff = Number(realized) - Number(expected);
  const text = `Plano ${id} concluído: esperado ${formatMoney(expected, updated.currency)}, realizado ${formatMoney(realized, updated.currency)} (diferença ${formatMoney(diff, updated.currency, { sign: true })}).`;
  return { plan: getDemoPlan(id, now), journal: { text, expected, realized, currency: updated.currency } };
}
