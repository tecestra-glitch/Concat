"use client";
import * as React from "react";
import * as TabsPrimitive from "@radix-ui/react-tabs";
import { cn } from "@/lib/utils";

export const Tabs = TabsPrimitive.Root;
export function TabsList({ className, ...props }: React.ComponentProps<typeof TabsPrimitive.List>) {
  return <TabsPrimitive.List className={cn("inline-flex h-9 items-center gap-1 rounded-md bg-surface-2 p-1 text-muted", className)} {...props} />;
}
export function TabsTrigger({ className, ...props }: React.ComponentProps<typeof TabsPrimitive.Trigger>) {
  return (
    <TabsPrimitive.Trigger
      className={cn(
        "inline-flex items-center justify-center rounded-sm px-3 py-1 text-sm font-medium whitespace-nowrap transition-colors focus-visible:outline-2 focus-visible:outline-ring data-[state=active]:bg-surface data-[state=active]:text-foreground data-[state=active]:shadow-xs",
        className,
      )}
      {...props}
    />
  );
}
export function TabsContent({ className, ...props }: React.ComponentProps<typeof TabsPrimitive.Content>) {
  return <TabsPrimitive.Content className={cn("mt-3 focus-visible:outline-2 focus-visible:outline-ring", className)} {...props} />;
}
