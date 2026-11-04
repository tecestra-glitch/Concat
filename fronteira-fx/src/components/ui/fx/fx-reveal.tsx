/**
 * Entrada de tela: envolve o conteúdo de cada rota (usado por `src/app/template.tsx`). Movimento de 4 px e opacidade
 * em --motion-base; com movimento reduzido a tela aparece direto (globals.css, §3.4). Não é elemento Uiverse.
 */
import * as React from "react";
import { cn } from "@/lib/utils";

export function FxReveal({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={cn("fx-enter", className)}>{children}</div>;
}
