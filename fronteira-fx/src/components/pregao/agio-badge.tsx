"use client";
import type { ReactElement } from "react";
import { directionOf } from "@/components/pregao/delta";
import { Badge } from "@/components/ui/badge";
import { formatPercent } from "@/lib/format";
import { cn } from "@/lib/utils";

const AGIO_TITLE = "Ágio em relação à referência (BCP/dolarPy)";

export interface AgioBadgeProps {
  /** Ágio por lado contra a referência, já ×100 (`1.1784` = 1,18 %); `null` = sem referência. */
  value: number | null;
  className?: string;
}

export function agioLabel(value: number | null): { text: string; sr: string } {
  if (value === null) return { text: "—", sr: "sem referência" };
  const sr = value > 0 ? "acima da referência" : value < 0 ? "abaixo da referência" : "igual à referência";
  return { text: formatPercent(value / 100, { sign: true }), sr };
}

/** Badge de ágio em cor neutra (`outline`): a direção vai no sinal e no texto `sr-only`, não na cor. */
export function AgioBadge({ value, className }: AgioBadgeProps): ReactElement {
  const { text, sr } = agioLabel(value);
  return (
    <Badge
      variant="outline"
      className={cn("tnum", className)}
      title={AGIO_TITLE}
      data-direction={directionOf(value)}
      data-testid="pregao-agio-badge"
    >
      {text}
      <span className="sr-only">{sr}</span>
    </Badge>
  );
}
