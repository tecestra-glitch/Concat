/**
 * Regras de tela dos planos de execução (fase A: nada executa dinheiro). Espelham o backend
 * (`services/plans.py`): expiração pela cotação mais velha só antes do primeiro passo, passos em ordem.
 * Puras e sem React, para serem testadas sem DOM.
 */
import type { Plan, PlanStatus, PlanStep } from "./api/types";
import { dec } from "./graph";
import { toNumber } from "./format";

export const PLAN_STATUS_LABEL: Record<PlanStatus, string> = {
  proposed: "Proposto",
  approved: "Aprovado",
  in_progress: "Em andamento",
  done: "Concluído",
  rejected: "Recusado",
  expired: "Expirado",
};

/** Momento (ms) em que a cotação mais velha do plano deixa de valer. */
export function quoteDeadlineMs(plan: Pick<Plan, "quotes_as_of" | "quote_max_age_s">): number {
  return Date.parse(plan.quotes_as_of) + plan.quote_max_age_s * 1000;
}

/**
 * Aplica o relógio: um plano que ainda não começou (proposto ou aprovado, sem passo feito) vira `expired`
 * quando a cotação mais velha passa do limite. Depois do primeiro passo ou de uma decisão final, nada muda.
 */
export function applyPlanClock(plan: Plan, now: number): Plan {
  if ((plan.status === "proposed" || plan.status === "approved") && now >= quoteDeadlineMs(plan)) return { ...plan, status: "expired" };
  return plan;
}

export function nextPendingStep(plan: Plan): PlanStep | null {
  return [...plan.steps].sort((a, b) => a.n - b.n).find((s) => s.status === "pending") ?? null;
}

export function canApprove(plan: Plan, now: number): boolean {
  return applyPlanClock(plan, now).status === "proposed";
}

export function canReject(plan: Plan, now: number): boolean {
  const s = applyPlanClock(plan, now).status;
  return s === "proposed" || s === "approved";
}

/** Só o próximo passo pendente, e só com o plano aprovado (ou já em andamento). */
export function canCompleteStep(plan: Plan, n: number, now: number): boolean {
  const s = applyPlanClock(plan, now).status;
  if (s !== "approved" && s !== "in_progress") return false;
  return nextPendingStep(plan)?.n === n;
}

export interface PlanResult {
  expected: string;
  realized: string;
  difference: string;
}

/** Esperado × realizado de um plano concluído: o realizado é o valor informado no último passo. */
export function resultOf(plan: Plan): PlanResult | null {
  if (plan.status !== "done") return null;
  const last = [...plan.steps].sort((a, b) => a.n - b.n).at(-1);
  const realized = last?.actual_out;
  const r = toNumber(realized);
  const e = toNumber(plan.amount_out_expected);
  if (realized === null || realized === undefined || r === null || e === null) return null;
  return { expected: plan.amount_out_expected, realized, difference: dec(r - e, 8) };
}

/** Quantos passos já foram feitos, para a barra de progresso. */
export function progressOf(plan: Plan): { done: number; total: number } {
  return { done: plan.steps.filter((s) => s.status === "done").length, total: plan.steps.length };
}
