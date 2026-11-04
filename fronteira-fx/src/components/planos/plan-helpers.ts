/** Textos e rótulos dos planos (pt-BR simples). Puro, para teste sem DOM. */
import type { PlanStatus } from "@/lib/api/types";
import type { BadgeVariant } from "@/components/ui/badge";

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
