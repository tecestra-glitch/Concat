"use client";
import type { ReactElement } from "react";
import { Landmark } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export interface ReferenceBadgeProps {
  /** Só o ícone visível; o texto "Referência" fica em `sr-only`. */
  compact?: boolean;
  /** Nome da fonte, acrescentado ao `title` (" Fonte: BCP."). */
  source?: string;
  className?: string;
}

const TITLE = "Preço de referência (BCP/dolarPy). Não é executável.";

/** Selo de referência: BCP/dolarPy nunca são preço executável nem contraparte (§0.1 item 5). */
export function ReferenceBadge({ compact = false, source, className }: ReferenceBadgeProps): ReactElement {
  const title = source ? `${TITLE} Fonte: ${source}.` : TITLE;
  return (
    <Badge variant="outline" className={cn("gap-1 border-dashed", className)} title={title} data-testid="pregao-reference-badge" data-compact={compact ? "true" : undefined}>
      <Landmark size={12} aria-hidden />
      {compact ? <span className="sr-only">Referência</span> : "Referência"}
    </Badge>
  );
}
