"use client";
import * as React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";
import { SettingsProvider } from "@/lib/settings";
import { LiveProvider } from "@/lib/live";
import { TooltipProvider } from "@/components/ui/tooltip";

export function Providers({ children }: { children: React.ReactNode }) {
  const [qc] = React.useState(() => new QueryClient({ defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } } }));
  return (
    <ThemeProvider attribute="class" defaultTheme="dark" enableSystem={false} disableTransitionOnChange>
      <QueryClientProvider client={qc}>
        <SettingsProvider>
          <LiveProvider>
            <TooltipProvider delayDuration={200}>{children}</TooltipProvider>
          </LiveProvider>
        </SettingsProvider>
      </QueryClientProvider>
    </ThemeProvider>
  );
}
