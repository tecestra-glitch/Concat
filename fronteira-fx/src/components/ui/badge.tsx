import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-sm border px-1.5 py-0.5 text-[11px] font-medium leading-4 whitespace-nowrap",
  {
    variants: {
      variant: {
        default: "border-transparent bg-surface-2 text-foreground",
        accent: "border-transparent bg-accent/15 text-accent",
        gain: "border-transparent bg-gain/15 text-gain",
        loss: "border-transparent bg-loss/15 text-loss",
        warn: "border-transparent bg-warn/15 text-warn",
        outline: "border-border text-muted",
      },
    },
    defaultVariants: { variant: "default" },
  },
);

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement>, VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}
