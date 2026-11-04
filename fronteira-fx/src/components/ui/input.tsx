import * as React from "react";
import { cn } from "@/lib/utils";

/**
 * Campo de entrada. Elemento Uiverse «campo-entrada» (BurgiSimon), MIT, Uiverse.io. Contorno --control-border (3:1),
 * foco com borda --accent e fundo --surface-2; placeholder --muted. Alvo mínimo de 44 px no toque.
 */
export function Input({ className, type, ...props }: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      type={type}
      className={cn(
        "flex h-9 w-full rounded-control border border-control-border bg-surface px-3 py-1 text-body text-foreground transition-colors duration-(--motion-fast) placeholder:text-muted focus:border-accent focus:bg-surface-2 focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-1 disabled:cursor-not-allowed disabled:opacity-50 max-sm:h-11",
        className,
      )}
      {...props}
    />
  );
}

export function Label({ className, ...props }: React.LabelHTMLAttributes<HTMLLabelElement>) {
  return <label className={cn("text-label font-medium text-muted", className)} {...props} />;
}
