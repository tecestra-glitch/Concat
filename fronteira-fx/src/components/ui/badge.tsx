import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

/** DS10: 12 px; `reference` (não executável) e `incomplete` (custo desconhecido) têm contorno tracejado. */
const badgeVariants = cva("inline-flex items-center gap-1 rounded-sm border px-1.5 py-0.5 text-xs font-medium leading-4 whitespace-nowrap", {
  variants: {
    variant: {
      default: "border-transparent bg-surface-2 text-foreground",
      accent: "border-transparent bg-accent/15 text-accent",
      gain: "border-transparent bg-gain/15 text-gain",
      loss: "border-transparent bg-loss/15 text-loss",
      warn: "border-transparent bg-warn/15 text-warn",
      outline: "border-border text-muted",
      reference: "border-dashed border-border-strong text-muted",
      incomplete: "border-dashed border-warn/70 bg-warn/10 text-warn",
    },
  },
  defaultVariants: { variant: "default" },
});

export type BadgeVariant = NonNullable<VariantProps<typeof badgeVariants>["variant"]>;
export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement>, VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}
