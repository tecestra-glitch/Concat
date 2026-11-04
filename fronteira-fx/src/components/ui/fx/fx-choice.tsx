"use client";
/**
 * Crédito Uiverse.io: slug `seletor-lista`; elemento Na3ar-17_fast-turtle-85; autor Na3ar-17; licença MIT; link https://uiverse.io/Na3ar-17/fast-turtle-85
 * Texto completo da licença: docs/creditos-uiverse.md.
 */
/**
 * Opção de lista com seleção (radio). Elemento Uiverse «seletor-lista» (Na3ar-17), MIT, Uiverse.io. Sem o overshoot
 * do original (easing --ease-out); o pulso ao marcar foi removido. Selecionado: fundo `accent-soft` e borda accent.
 */
import * as React from "react";
import { cn } from "@/lib/utils";

export interface FxChoiceProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  checked: boolean;
}

export const FxChoice = React.forwardRef<HTMLButtonElement, FxChoiceProps>(function FxChoice({ checked, className, children, ...props }, ref) {
  return (
    <button
      ref={ref}
      type="button"
      role="radio"
      aria-checked={checked}
      className={cn(
        "tnum inline-flex min-h-11 min-w-11 items-center justify-center rounded-chip border border-transparent px-3 text-body font-medium transition-colors duration-(--motion-fast) sm:min-h-8 sm:min-w-10 sm:px-2.5",
        "focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2 disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50",
        checked ? "border-accent bg-accent-soft text-foreground" : "text-muted hover:bg-surface-3 hover:text-foreground",
        className,
      )}
      {...props}
    >
      {children}
    </button>
  );
});
