/**
 * Esqueleto com brilho. Inspirado no elemento Uiverse «esqueleto-shimmer» (arshshaikh06), MIT, Uiverse.io. O brilho
 * é implementado do zero em globals.css (`.fx-skeleton`); nenhum código do original foi copiado. Com movimento
 * reduzido o bloco fica estático, com a cor base.
 */
import * as React from "react";
import { cn } from "@/lib/utils";

export function FxSkeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div aria-hidden="true" className={cn("fx-skeleton rounded-control", className)} {...props} />;
}
