"use client";
import * as React from "react";
import * as TabsPrimitive from "@radix-ui/react-tabs";
import { cn } from "@/lib/utils";

/** Abas (Radix). Hover por cor; cada aba tem alvo de 44 px no celular (min-h-11), sombra de nível 1 só na aba ativa. */
export const Tabs = TabsPrimitive.Root;
export function TabsList({ className, ...props }: React.ComponentProps<typeof TabsPrimitive.List>) {
  return <TabsPrimitive.List className={cn("flex h-auto min-h-9 max-w-full items-center gap-1 overflow-x-auto rounded-control bg-surface-2 p-1 text-muted sm:inline-flex sm:h-9", className)} {...props} />;
}
export function TabsTrigger({ className, ...props }: React.ComponentProps<typeof TabsPrimitive.Trigger>) {
  return (
    <TabsPrimitive.Trigger
      className={cn(
        "inline-flex items-center justify-center whitespace-nowrap rounded-chip px-3 py-1 text-body font-medium transition-colors duration-(--motion-fast) hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring max-sm:min-h-11 data-[state=active]:bg-surface data-[state=active]:text-foreground data-[state=active]:shadow-[var(--shadow-1)]",
        className,
      )}
      {...props}
    />
  );
}
export function TabsContent({ className, ...props }: React.ComponentProps<typeof TabsPrimitive.Content>) {
  return <TabsPrimitive.Content className={cn("mt-3 focus-visible:outline-2 focus-visible:outline-ring", className)} {...props} />;
}
