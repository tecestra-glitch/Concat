/**
 * Cartão com linha de luz no hover. Elemento Uiverse «cartao-hover» (Admin12121), MIT, Uiverse.io. A linha é um
 * pseudo-elemento que muda só a opacidade (240 ms); sem box-shadow animado. Fundo, borda e sombra vêm dos tokens.
 */
import * as React from "react";
import { cn } from "@/lib/utils";

export function FxCard({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("fx-card rounded-surface border border-border bg-surface text-foreground shadow-[var(--shadow-1)]", className)} {...props} />;
}
