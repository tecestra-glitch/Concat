"use client";
/**
 * Crédito Uiverse.io: slug `campo-entrada`; elemento BurgiSimon_rotten-dolphin-78; autor BurgiSimon; licença MIT; link https://uiverse.io/BurgiSimon/rotten-dolphin-78
 * Texto completo da licença: docs/creditos-uiverse.md.
 */
import * as React from "react";
import * as SelectPrimitive from "@radix-ui/react-select";
import { Check, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * Select. Campo: elemento Uiverse «campo-entrada» (BurgiSimon). Item destacado com anel `--ring` interno de 2 px
 * (G2: contraste ≥ 3:1 contra o item), para o foco por teclado aparecer mesmo sem a cor de fundo.
 */
export const Select = SelectPrimitive.Root;
export const SelectValue = SelectPrimitive.Value;

export function SelectTrigger({ className, children, ...props }: React.ComponentProps<typeof SelectPrimitive.Trigger>) {
  return (
    <SelectPrimitive.Trigger
      className={cn(
        "flex h-9 w-full items-center justify-between gap-2 rounded-control border border-control-border bg-surface px-3 py-2 text-body text-foreground transition-colors duration-(--motion-fast) focus:border-accent focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-1 disabled:opacity-50 max-sm:h-11 [&>span]:truncate",
        className,
      )}
      {...props}
    >
      {children}
      <SelectPrimitive.Icon asChild>
        <ChevronDown className="size-4 text-muted" aria-hidden />
      </SelectPrimitive.Icon>
    </SelectPrimitive.Trigger>
  );
}

export function SelectContent({ className, children, position = "popper", ...props }: React.ComponentProps<typeof SelectPrimitive.Content>) {
  return (
    <SelectPrimitive.Portal>
      <SelectPrimitive.Content
        position={position}
        className={cn(
          "fx-pop z-(--z-overlay) max-h-72 min-w-[8rem] overflow-hidden rounded-control border border-border bg-surface text-foreground shadow-[var(--shadow-2)]",
          position === "popper" && "data-[side=bottom]:translate-y-1 w-(--radix-select-trigger-width)",
          className,
        )}
        {...props}
      >
        <SelectPrimitive.Viewport className="p-1">{children}</SelectPrimitive.Viewport>
      </SelectPrimitive.Content>
    </SelectPrimitive.Portal>
  );
}

export function SelectItem({ className, children, ...props }: React.ComponentProps<typeof SelectPrimitive.Item>) {
  return (
    <SelectPrimitive.Item
      className={cn(
        "relative flex w-full cursor-default select-none items-center rounded-chip py-1.5 pl-7 pr-2 text-body outline-none transition-colors duration-(--motion-fast) focus:bg-surface-2 data-[highlighted]:bg-surface-2 data-[highlighted]:ring-2 data-[highlighted]:ring-ring data-[highlighted]:ring-inset data-[disabled]:opacity-50",
        className,
      )}
      {...props}
    >
      <span className="absolute left-2 flex size-3.5 items-center justify-center">
        <SelectPrimitive.ItemIndicator>
          <Check className="size-3.5" aria-hidden />
        </SelectPrimitive.ItemIndicator>
      </span>
      <SelectPrimitive.ItemText>{children}</SelectPrimitive.ItemText>
    </SelectPrimitive.Item>
  );
}
