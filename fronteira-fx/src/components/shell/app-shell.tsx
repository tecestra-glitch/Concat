"use client";
import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Ellipsis } from "lucide-react";
import { cn } from "@/lib/utils";
import { NAV, isActive, splitNav } from "./nav";
import { TopBar } from "./top-bar";
import { DemoBanner } from "./demo-banner";
import { AlertToaster } from "./alert-toaster";
import { Dialog, DialogContent, DialogDescription, DialogTitle, DialogTrigger } from "@/components/ui/dialog";

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  // A tela de entrada não mostra o terminal: fica sem menu, barra nem faixa de demonstração.
  if (pathname === "/entrar") return <>{children}</>;
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
            const active = isActive(item.href, pathname);
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
        <p className="px-4 py-3 text-xs leading-4 text-muted">BRL · USD · PYG — CDE · ASU · PJC</p>
      </aside>
      <div className="flex min-w-0 flex-col">
        <DemoBanner />
        <TopBar />
        <main id="conteudo" className="flex-1 px-4 pb-24 pt-4 sm:px-6 lg:pb-8">
          {children}
        </main>
        <AlertToaster />
        <MobileNav pathname={pathname} />
      </div>
    </div>
  );
}

/** U7: 4 rotas fixas + «Mais» com todas as outras, para nenhuma tela ficar sem caminho no celular. */
function MobileNav({ pathname }: { pathname: string }) {
  const { primary, more } = splitNav(NAV);
  const moreActive = more.some((n) => isActive(n.href, pathname));
  const [open, setOpen] = React.useState(false);
  const itemClass = (active: boolean) => cn("flex min-h-12 w-full flex-col items-center justify-center gap-0.5 py-2 text-caption text-muted focus-visible:outline-2 focus-visible:outline-ring", active && "text-accent");
  return (
    <nav aria-label="Navegação" data-testid="mobile-nav" className="fixed inset-x-0 bottom-0 z-40 border-t border-border bg-surface/95 backdrop-blur lg:hidden">
      <ul className="grid" style={{ gridTemplateColumns: `repeat(${primary.length + 1}, minmax(0, 1fr))` }}>
        {primary.map((item) => {
          const active = isActive(item.href, pathname);
          return (
            <li key={item.href}>
              <Link href={item.href} aria-current={active ? "page" : undefined} className={itemClass(active)}>
                <item.icon className="size-5" aria-hidden />
                {item.short}
              </Link>
            </li>
          );
        })}
        <li>
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
              <button type="button" className={itemClass(moreActive)} aria-label="Mais telas" aria-haspopup="dialog">
                <Ellipsis className="size-5" aria-hidden />
                Mais
              </button>
            </DialogTrigger>
            <DialogContent className="max-w-sm" data-testid="more-menu">
              <DialogTitle>Mais telas</DialogTitle>
              <DialogDescription>Todas as outras telas do terminal.</DialogDescription>
              <nav className="grid gap-1" aria-label="Outras telas">
                {more.map((n) => (
                  <Link key={n.href} href={n.href} onClick={() => setOpen(false)} aria-current={isActive(n.href, pathname) ? "page" : undefined} className={cn("flex min-h-11 items-center gap-2 rounded-md px-2 py-2 text-sm hover:bg-surface-2", isActive(n.href, pathname) && "bg-surface-2 font-medium")}>
                    <n.icon className="size-4" aria-hidden /> {n.label}
                  </Link>
                ))}
              </nav>
            </DialogContent>
          </Dialog>
        </li>
      </ul>
    </nav>
  );
}
