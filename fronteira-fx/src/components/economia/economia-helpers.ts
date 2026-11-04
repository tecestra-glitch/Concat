/**
 * Funções puras da tela Economia e cripto: selo de volatilidade, formatação de referências e variações.
 * Dinheiro e taxas chegam como string decimal; converte-se só aqui, para exibir (pt-BR).
 */
import type { BadgeVariant } from "@/components/ui/badge";
import { formatDateTime } from "@/lib/format";
import { MARKET_SOURCE_LABEL, type MarketVolatility, type NewsItem } from "@/lib/api/market";

export interface VolatilityView {
  label: string;
  variant: BadgeVariant;
  /** Texto para leitor de tela e tooltip. */
  description: string;
}

const REGIME_LABEL = { normal: "normal", alta: "alta", muito_alta: "muito alta" } as const;

/**
 * Selo: normal / alta / muito alta. Sem dados suficientes ou com dados antigos o selo não diz regime nenhum:
 * mostra o estado, nunca um número inventado.
 */
export function volatilityView(v: MarketVolatility): VolatilityView {
  if (v.status === "insufficient_data") {
    return { label: "dados insuficientes", variant: "outline", description: "Ainda não há velas suficientes para medir a volatilidade." };
  }
  if (v.status === "stale_input") {
    return { label: "dados antigos", variant: "outline", description: "As últimas velas são antigas: a volatilidade atual não pode ser medida." };
  }
  if (!v.regime) {
    return { label: "dados insuficientes", variant: "outline", description: "Sem regime calculado para este instrumento." };
  }
  if (v.regime === "muito_alta") {
    return { label: REGIME_LABEL.muito_alta, variant: "loss", description: "Volatilidade muito alta: movimento acima de 3 vezes a média recente, ou regime de 1 dia acima de 2 vezes o de 20 dias." };
  }
  if (v.regime === "alta") {
    return { label: REGIME_LABEL.alta, variant: "warn", description: "Volatilidade alta: regime de 1 dia acima de 1,5 vez o de 20 dias, ou movimento acima de 2 vezes a média recente." };
  }
  return { label: REGIME_LABEL.normal, variant: "default", description: "Volatilidade normal para o período recente." };
}

const pt = (maximumFractionDigits: number, minimumFractionDigits = 0) =>
  new Intl.NumberFormat("pt-BR", { maximumFractionDigits, minimumFractionDigits });

/** Preço de referência: até 4 casas acima de 1 (6 abaixo), sem zeros à direita, separador de milhar pt-BR. */
export function formatReference(value: string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  return pt(Math.abs(n) >= 1 ? 4 : 6).format(n);
}

/** Variação em % com sinal explícito (`+0,88 %`, `-1,18 %`). `null` (sem base de comparação) vira traço. */
export function formatChangePct(value: string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  const sign = n > 0 ? "+" : "";
  return `${sign}${pt(2, 2).format(n)} %`;
}

export function changeTone(value: string | null | undefined): "gain" | "loss" | "muted" {
  const n = Number(value);
  if (value === null || value === undefined || !Number.isFinite(n) || n === 0) return "muted";
  return n > 0 ? "gain" : "loss";
}

/** Percentual de volatilidade já em %, com 2 casas. */
export function formatVolPct(value: string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  return `${pt(2, 2).format(n)} %`;
}

export function sourceLabel(source: string): string {
  return MARKET_SOURCE_LABEL[source] ?? source;
}

/** Horário da manchete: publicação quando houver, senão captura. */
export function newsMoment(item: NewsItem): { iso: string; label: string } {
  const iso = item.published_at ?? item.captured_at;
  return { iso, label: formatDateTime(iso) };
}

/** Só http(s) é levado a `href`: qualquer outro esquema vira texto, nunca link. */
export function safeExternalHref(link: string): string | null {
  try {
    const url = new URL(link);
    return url.protocol === "https:" || url.protocol === "http:" ? url.toString() : null;
  } catch {
    return null;
  }
}
