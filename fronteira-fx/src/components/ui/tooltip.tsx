"use client";
/**
 * Crédito Uiverse.io: slug `tooltip-escuro`; elemento SouravBandyopadhyay_ugly-pug-52; autor SouravBandyopadhyay; licença MIT; link https://uiverse.io/SouravBandyopadhyay/ugly-pug-52
 * Texto completo da licença: docs/creditos-uiverse.md.
 */
import * as React from "react";
import * as TooltipPrimitive from "@radix-ui/react-tooltip";
import { cn } from "@/lib/utils";

export const TooltipProvider = TooltipPrimitive.Provider;
export const Tooltip = TooltipPrimitive.Root;
export const TooltipTrigger = TooltipPrimitive.Trigger;

/** Balão do tooltip: entrada em --motion-fast (`fx-pop`), sombra de nível 2. Ver `fx/fx-tooltip.tsx` para as siglas. */
export function TooltipContent({ className, sideOffset = 4, ...props }: React.ComponentProps<typeof TooltipPrimitive.Content>) {
  return (
    <TooltipPrimitive.Portal>
      <TooltipPrimitive.Content
        sideOffset={sideOffset}
        className={cn("fx-pop z-(--z-overlay) max-w-xs rounded-control border border-border bg-surface px-3 py-1.5 text-caption text-foreground shadow-[var(--shadow-2)]", className)}
        {...props}
      />
    </TooltipPrimitive.Portal>
  );
}
