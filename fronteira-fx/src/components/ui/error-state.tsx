"use client";
import { RefreshCw } from "lucide-react";
import { Button } from "./button";
import { cn } from "@/lib/utils";

/** DS11: erro com «Tentar de novo» e detalhes recolhíveis. Diz o que falhou, sem pedir desculpas. */
export function ErrorState({ title = "Não foi possível carregar", error, onRetry, retryLabel = "Tentar de novo", className, compact = false }: { title?: string; error?: unknown; onRetry?: () => void; retryLabel?: string; className?: string; compact?: boolean }) {
  const detail = error instanceof Error ? error.message : typeof error === "string" ? error : null;
  return (
    <div role="alert" className={cn("rounded-control border border-loss/40 bg-loss/5 text-sm", compact ? "p-3" : "p-4", className)}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="font-medium text-loss">{title}</p>
        {onRetry && (
          <Button type="button" size="sm" variant="secondary" onClick={onRetry}>
            <RefreshCw aria-hidden /> {retryLabel}
          </Button>
        )}
      </div>
      {detail && (
        <details className="mt-2 text-xs text-muted">
          <summary className="cursor-pointer select-none">Detalhes</summary>
          <p className="mt-1 break-words font-mono">{detail}</p>
        </details>
      )}
    </div>
  );
}
