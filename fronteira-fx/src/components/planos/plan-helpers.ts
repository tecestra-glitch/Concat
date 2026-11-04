/** Textos e rótulos dos planos (pt-BR simples). Puro, para teste sem DOM. */
import type { Confidence, Currency, PlanStatus } from "@/lib/api/types";
import type { BadgeVariant } from "@/components/ui/badge";
import { formatMoney, toNumber } from "@/lib/format";

export const PLAN_TONE: Record<PlanStatus, BadgeVariant> = {
  proposed: "accent",
  approved: "gain",
  in_progress: "warn",
  done: "gain",
  rejected: "outline",
  expired: "loss",
};

/** Aviso fixo na tela do plano: aprovar não move dinheiro. */
export const NO_MONEY_MOVED = "Aprovar não move dinheiro. O Fronteira FX só registra a sua decisão e os valores que você informar. Cada passo você faz por conta própria, fora do app.";

/** Parte de um texto de passo em ordem legível: "2 de 4". */
export function stepCounter(n: number, total: number): string {
  return `${n} de ${total}`;
}

export const STEP_STATUS_LABEL = { done: "Feito", pending: "Pendente" } as const;

/**
 * Ganho do plano para exibir. Ganho com custo pendente (`incomplete`) é estimativa: sai com "≈", sem sinal e em
 * tom neutro. Só ganho confirmado ganha "+" e tom de ganho; prejuízo sai em tom de perda.
 */
export function gainPresentation(value: string, currency: Currency, confidence: Confidence): { text: string; tone: "gain" | "loss" | "muted" } {
  const incomplete = confidence === "incomplete";
  const n = toNumber(value) ?? 0;
  const tone = incomplete || n === 0 ? "muted" : n > 0 ? "gain" : "loss";
  return { text: `${incomplete ? "≈ " : ""}${formatMoney(value, currency, { sign: !incomplete })}`, tone };
}

const COST_LABEL: Record<"spread" | "fees" | "iof" | "transport", string> = { spread: "spread", fees: "tarifas", iof: "IOF", transport: "deslocamento" };

/** Custos que faltam no plano, pelo nome em português (`null` = desconhecido). */
export function unknownCostLabels(costs: Partial<Record<keyof typeof COST_LABEL, string | null>> | null | undefined): string[] {
  if (!costs) return [];
  return (Object.keys(COST_LABEL) as Array<keyof typeof COST_LABEL>).filter((k) => costs[k] === null).map((k) => COST_LABEL[k]);
}

/** Contagem da cotação em linguagem comum: "15 min", "9 min 9 s", "9 s". Nunca parece hora do dia. */
export function formatPlanCountdown(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  if (s < 60) return `${s} s`;
  const m = Math.floor(s / 60);
  const r = s % 60;
  return r === 0 ? `${m} min` : `${m} min ${r} s`;
}
