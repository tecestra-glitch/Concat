"use client";
/**
 * Crédito Uiverse.io: slug `alternador`; elemento Voxybuns_horrible-shrimp-47; autor Voxybuns; licença MIT; link https://uiverse.io/Voxybuns/horrible-shrimp-47
 * Texto completo da licença: docs/creditos-uiverse.md.
 */
import * as React from "react";
import * as SwitchPrimitive from "@radix-ui/react-switch";
import { cn } from "@/lib/utils";

/**
 * Interruptor. Elemento Uiverse «alternador» (Voxybuns), MIT, Uiverse.io. Trilha 44 × 24 px, contorno --control-border
 * (3:1 sobre a superfície, WCAG 1.4.11); ativo em --accent. A área de toque no celular é ampliada por pseudo-elemento
 * (44 px de altura), sem mudar o desenho.
 */
export function Switch({ className, ...props }: React.ComponentProps<typeof SwitchPrimitive.Root>) {
  return (
    <SwitchPrimitive.Root
      className={cn(
        "peer relative inline-flex h-6 w-11 shrink-0 cursor-pointer items-center rounded-full border border-control-border bg-surface-3 transition-colors duration-(--motion-fast)",
        "before:absolute before:-inset-x-1 before:-inset-y-2.5 before:content-[''] max-sm:before:-inset-y-2.5",
        "focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2 disabled:cursor-not-allowed disabled:opacity-50",
        "data-[state=checked]:border-accent data-[state=checked]:bg-accent",
        className,
      )}
      {...props}
    >
      <SwitchPrimitive.Thumb className="pointer-events-none block size-4 translate-x-1 rounded-full bg-foreground transition-transform duration-(--motion-base) ease-(--ease-inout) data-[state=checked]:translate-x-6 data-[state=checked]:bg-accent-foreground" />
    </SwitchPrimitive.Root>
  );
}
