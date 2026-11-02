"use client";
import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { NAV } from "./nav";
import { TopBar } from "./top-bar";
import { DemoBanner } from "./demo-banner";

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  return (
    <div className="min-h-dvh lg:grid lg:grid-cols-[13.5rem_1fr]">
      <a href="#conteudo" className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-[60] focus:rounded-md focus:bg-accent focus:px-3 focus:py-2 focus:text-accent-foreground">
        Ir para o conteúdo
      </a>
      <aside className="hidden lg:flex lg:flex-col lg:border-r lg:border-border lg:bg-surface" aria-label="Navegação principal">
        <div className="flex h-14 items-center gap-2 border-b border-border px-4">
          <span aria-hidden className="inline-block size-2.5 rounded-sm bg-accent" />
          <span className="text-sm font-semibold tracking-tight">Fronteira FX</span>
        </div>
        <nav className="flex-1 space-y-0.5 p-2">
          {NAV.map((item) => {
            const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "flex items-center gap-2.5 rounded-md px-2.5 py-2 text-sm text-muted transition-colors hover:bg-surface-2 hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring",
                  active && "bg-surface-2 text-foreground font-medium",
                )}
              >
                <item.icon className="size-4" aria-hidden />
                {item.label}
              </Link>
            );
          })}
        </nav>
        <p className="px-4 py-3 text-[11px] leading-4 text-muted">BRL · USD · PYG — CDE · ASU · PJC</p>
      </aside>
      <div className="flex min-w-0 flex-col">
        <DemoBanner />
        <TopBar />
        <main id="conteudo" className="flex-1 px-4 pb-24 pt-4 sm:px-6 lg:pb-8">
          {children}
        </main>
        <MobileNav pathname={pathname} />
      </div>
    </div>
  );
}

function MobileNav({ pathname }: { pathname: string }) {
  return (
    <nav aria-label="Navegação" className="fixed inset-x-0 bottom-0 z-40 border-t border-border bg-surface/95 backdrop-blur lg:hidden">
      <ul className="grid grid-cols-5">
        {NAV.slice(0, 5).map((item) => {
          const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
          return (
            <li key={item.href}>
              <Link
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={cn("flex flex-col items-center gap-0.5 py-2 text-[10px] text-muted focus-visible:outline-2 focus-visible:outline-ring", active && "text-accent")}
              >
                <item.icon className="size-5" aria-hidden />
                {item.short}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
