"use client";
import * as React from "react";
import { usePathname } from "next/navigation";
import { Menu, Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import Link from "next/link";
import { NAV } from "./nav";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { ConnectionStatus } from "./connection-status";
import { useMounted } from "@/lib/use-now";

export function TopBar() {
  const pathname = usePathname();
  const current = NAV.find((n) => (n.href === "/" ? pathname === "/" : pathname.startsWith(n.href)));
  return (
    <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-border bg-background/90 px-4 backdrop-blur sm:px-6">
      <Dialog>
        <DialogTrigger asChild>
          <Button variant="ghost" size="icon" className="shrink-0 lg:hidden" aria-label="Abrir menu">
            <Menu />
          </Button>
        </DialogTrigger>
        <DialogContent className="max-w-xs">
          <DialogTitle>Fronteira FX</DialogTitle>
          <nav className="grid gap-1">
            {NAV.map((n) => (
              <Link key={n.href} href={n.href} className="flex items-center gap-2 rounded-md px-2 py-2 text-sm hover:bg-surface-2">
                <n.icon className="size-4" aria-hidden /> {n.label}
              </Link>
            ))}
          </nav>
        </DialogContent>
      </Dialog>
      <h1 className="truncate text-heading font-semibold sm:text-title">{current?.label ?? "Fronteira FX"}</h1>
      <div className="ml-auto flex items-center gap-2">
        <ConnectionStatus />
        <ThemeToggle />
      </div>
    </header>
  );
}

/** Alternância de tema (G8): rótulo fixo "Alternar tema"; `aria-pressed` vale quando o tema claro está ligado. */
function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();
  const mounted = useMounted();
  const dark = mounted ? resolvedTheme === "dark" : true;
  return (
    <Button variant="ghost" size="icon" aria-label="Alternar tema" aria-pressed={!dark} title={dark ? "Tema escuro (ativar claro)" : "Tema claro (ativar escuro)"} onClick={() => setTheme(dark ? "light" : "dark")}>
      {dark ? <Sun /> : <Moon />}
    </Button>
  );
}
