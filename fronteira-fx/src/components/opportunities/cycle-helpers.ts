import type { Currency, Cycle, Leg, LegKind, RouteChannel } from "@/lib/api/types";
import { formatMoney, toNumber } from "@/lib/format";

/** Perna de fronteira acima deste valor em US$ pede declaração (aviso, não bloqueio). */
export const NEEDS_DECLARATION_USD = 10_000;

export const CYCLE_CURRENCIES: Currency[] = ["BRL", "USD", "PYG"];

/** Caminho de um ciclo em texto: "BRL@brbank → USD@nomad → BRL@brbank" vira "BRL · brbank → USD · nomad → BRL · brbank". */
export function pathLabel(path: string[]): string {
  return path.map((n) => n.replace("@", " · ")).join(" → ");
}

/** Moeda do nó inicial (`BRL@brbank` → BRL). */
export function cycleCurrency(node: string): Currency {
  return node.split("@")[0] as Currency;
}

/**
 * Ganho do ciclo em uma moeda, em número (só para ordenar e comparar). `null` quando não dá para converter:
 * nunca se trata a falta de taxa como zero.
 */
export function cycleGain(c: Cycle, currency: Currency): number | null {
  if (c.gain_by_currency) return toNumber(c.gain_by_currency[currency]);
  return currency === cycleCurrency(c.start) ? toNumber(c.gain) : null;
}

/** Lucrativo = ganho na moeda de partida positivo (D1: string decimal, comparado como número). */
export function isProfitable(c: Cycle): boolean {
  return (toNumber(c.gain) ?? 0) > 0;
}

export function formatMinutes(minutes: number): string {
  return minutes >= 1440 ? `${(minutes / 1440).toFixed(1).replace(".", ",")} d` : `${minutes} min`;
}

export interface CycleFilter {
  /** "all" ou a moeda de partida. */
  currency: Currency | "all";
  /** Texto digitado; vazio = sem ganho mínimo. */
  minGain: string;
  /** Moeda em que o ganho mínimo é medido. */
  minCurrency: Currency;
  includeIncomplete: boolean;
}

/**
 * Filtros da tela: moeda de partida, ganho mínimo (na moeda escolhida) e ciclos com custo pendente.
 * Ciclo sem conversão para a moeda do mínimo não prova que passa, então sai da lista quando há mínimo.
 */
export function filterCycles(list: Cycle[], f: CycleFilter): Cycle[] {
  const min = f.minGain.trim() === "" ? null : toNumber(f.minGain);
  return list.filter((c) => {
    if (f.currency !== "all" && cycleCurrency(c.start) !== f.currency) return false;
    if (!f.includeIncomplete && c.confidence === "incomplete") return false;
    if (min !== null) {
      const g = cycleGain(c, f.minCurrency);
      if (g === null || g < min) return false;
    }
    return true;
  });
}

const KIND_WORD: Record<LegKind, string> = { exchange: "Troca", transfer: "Transferência", travel: "Deslocamento", deposit: "Depósito", withdraw: "Saque" };
const CHANNEL_WORD: Record<RouteChannel, string> = { presencial: "presencial", assistida: "assistida", automatizavel: "automatizável" };

/** Nome da perna em português simples: "Troca presencial", "Deslocamento", "Transferência assistida". */
export function legLabel(kind: LegKind, channel: RouteChannel): string {
  return kind === "exchange" || kind === "transfer" ? `${KIND_WORD[kind]} ${CHANNEL_WORD[channel]}` : KIND_WORD[kind];
}

export const CHANNEL_TEXT: Record<RouteChannel, string> = {
  presencial: "Presencial: exige ir até a casa, a cidade ou o balcão",
  assistida: "Assistida: feita no app do banco ou da fintech, com confirmação sua",
  automatizavel: "Automatizável: poderia ser feita por sistema (nenhuma rota hoje)",
};

/** Resumo de uma perna: "Pix → Nomad: R$ 5.000,00 → US$ 920,00". */
export function legText(leg: Leg): string {
  return `${leg.via}: ${formatMoney(leg.amount_in, cycleCurrency(leg.from))} → ${formatMoney(leg.amount_out, cycleCurrency(leg.to))}`;
}

export interface CostRow {
  label: string;
  value: string | null;
}

/** Quebra de custos na moeda de partida. `null` aparece como "não informado" na tela, nunca como zero. */
export function costRows(c: Cycle, currency: Currency): CostRow[] {
  const k = c.costs;
  const fmt = (v: string | null | undefined) => (v === null || v === undefined ? null : formatMoney(v, currency));
  return [
    { label: "Spread", value: fmt(k?.spread) },
    { label: "Tarifas", value: fmt(k?.fees) },
    { label: "IOF", value: fmt(k?.iof) },
    { label: "Deslocamento", value: fmt(k?.transport) },
  ];
}
