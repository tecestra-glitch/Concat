/**
 * DS8 — variação com sinal, seta e texto oculto. Verde/vermelho só aqui, e nunca como único sinal:
 * verde contra vermelho dá 1,4:1 entre si e quem tem deuteranopia não os distingue.
 */
import { formatPercent, toNumber } from "@/lib/format";
import { cn } from "@/lib/utils";

export type DeltaDirection = "up" | "down" | "flat" | "none";

export interface DeltaDescription {
  direction: DeltaDirection;
  arrow: "▲" | "▼" | "";
  srText: string;
}

export function describeDelta(value: string | number | null | undefined): DeltaDescription {
  const n = toNumber(value);
  if (n === null) return { direction: "none", arrow: "", srText: "sem variação conhecida" };
  if (n > 0) return { direction: "up", arrow: "▲", srText: "subiu" };
  if (n < 0) return { direction: "down", arrow: "▼", srText: "caiu" };
  return { direction: "flat", arrow: "", srText: "estável" };
}

const TONE: Record<DeltaDirection, string> = { up: "text-gain", down: "text-loss", flat: "text-muted", none: "text-muted" };

/**
 * `value` é uma razão (0.0041 = +0,41 %) por padrão; com `text` o chamador fornece o texto já
 * formatado (ex.: um ganho em dinheiro) e o componente só acrescenta seta, sinal e texto oculto.
 */
export function Delta({ value, text, className }: { value: string | number | null | undefined; text?: string; className?: string }) {
  const d = describeDelta(value);
  const body = text ?? (d.direction === "none" ? "—" : formatPercent(value, { sign: true }));
  return (
    <span className={cn("tnum inline-flex items-center gap-1", TONE[d.direction], className)}>
      {d.arrow && <span aria-hidden>{d.arrow}</span>}
      <span className="sr-only">{d.srText}: </span>
      {body}
    </span>
  );
}
