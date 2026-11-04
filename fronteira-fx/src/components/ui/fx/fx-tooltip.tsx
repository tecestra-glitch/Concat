"use client";
/**
 * Crédito Uiverse.io: slug `tooltip-escuro`; elemento SouravBandyopadhyay_ugly-pug-52; autor SouravBandyopadhyay; licença MIT; link https://uiverse.io/SouravBandyopadhyay/ugly-pug-52
 * Texto completo da licença: docs/creditos-uiverse.md.
 */
/**
 * Dica de siglas (spread, taxa efetiva, ROI). Elemento Uiverse «tooltip-escuro» (SouravBandyopadhyay), MIT, Uiverse.io.
 * O mecanismo é o do Radix (`role="tooltip"`, abre no foco e no hover); o original usava `attr()`, que não foi usado.
 * A caixa usa --surface-3 e texto --foreground; a animação é a de entrada, em --motion-fast.
 */
import * as React from "react";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

export function FxTooltip({ content, children, side = "top" }: { content: React.ReactNode; children: React.ReactElement; side?: "top" | "bottom" }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>{children}</TooltipTrigger>
      <TooltipContent side={side} className="bg-surface-3 text-foreground">
        {content}
      </TooltipContent>
    </Tooltip>
  );
}
