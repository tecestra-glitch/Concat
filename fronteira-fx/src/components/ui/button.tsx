import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

/**
 * Botões (dev/ui/spec-reforma-ui.md §4). `default` é o CTA em pílula (elemento Uiverse «botao-primario», sem o texto
 * "great work"); `ghost` é plano, com borda --border (elemento «botao-discreto-neumorfico», sem neumorfismo).
 * Hover troca a cor de fundo por --surface-2 ou --surface-3; nada de `hover:opacity-*`. Alvo de 44 px no toque.
 */
const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap text-body font-medium transition-colors duration-(--motion-fast) fx-press disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50 [&_svg]:size-4 [&_svg]:shrink-0 focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2",
  {
    variants: {
      variant: {
        default: "rounded-pill bg-accent text-accent-foreground hover:bg-[color-mix(in_oklab,var(--accent)_86%,var(--foreground))]",
        secondary: "rounded-control border border-border bg-surface-2 text-foreground hover:bg-surface-3",
        ghost: "rounded-control border border-border bg-transparent text-foreground hover:bg-surface-2",
        outline: "rounded-control border border-control-border bg-transparent text-foreground hover:bg-surface-2",
        destructive: "rounded-control bg-loss text-background hover:bg-[color-mix(in_oklab,var(--loss)_86%,var(--foreground))]",
      },
      size: {
        default: "h-9 px-4 py-2 max-sm:h-11",
        sm: "h-8 rounded-control px-3 text-caption max-sm:h-11",
        lg: "h-10 px-6 max-sm:h-11",
        icon: "size-9 max-sm:size-11",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export function Button({ className, variant, size, asChild = false, ...props }: ButtonProps) {
  const Comp = asChild ? Slot : "button";
  return <Comp className={cn(buttonVariants({ variant, size, className }))} {...props} />;
}
export { buttonVariants };
