"use client";
/** Toasts dos eventos `alert.fired` do stream (lidos de src/lib/alert-toasts.ts). Fica acima da barra do celular. */
import Link from "next/link";
import { BellRing, X } from "lucide-react";
import { alertToasts, useAlertToasts } from "@/lib/alert-toasts";
import { formatClock } from "@/lib/api/watch";

export function AlertToaster() {
  const toasts = useAlertToasts();
  if (toasts.length === 0) return null;
  return (
    <section aria-label="Alertas disparados" aria-live="polite" data-testid="alert-toasts" className="fixed bottom-20 right-3 z-50 flex w-[calc(100%-1.5rem)] max-w-sm flex-col gap-2 sm:right-4 lg:bottom-4">
      {toasts.slice(0, 3).map((t) => (
        <div key={t.id} role="status" className="flex items-start gap-2 rounded-md border border-border bg-surface p-3 text-sm shadow-lg">
          <BellRing className="mt-0.5 size-4 shrink-0 text-accent" aria-hidden />
          <div className="min-w-0 flex-1">
            <p className="break-words">{t.message}</p>
            <p className="mt-1 text-xs text-muted">
              <time dateTime={t.ts}>{formatClock(t.ts)}</time> · <Link href="/alertas" className="text-accent underline">ver alertas</Link>
            </p>
          </div>
          <button type="button" onClick={() => alertToasts.dismiss(t.id)} aria-label="Fechar alerta" className="rounded-sm p-1 text-muted hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring">
            <X className="size-4" aria-hidden />
          </button>
        </div>
      ))}
      {toasts.length > 3 && <p className="text-right text-xs text-muted">+{toasts.length - 3} alertas em /alertas</p>}
    </section>
  );
}
