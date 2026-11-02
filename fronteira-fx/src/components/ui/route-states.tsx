"use client";
import Link from "next/link";
import { Skeleton } from "./skeleton";
import { ErrorState } from "./error-state";
import { Button } from "./button";

/** Esqueleto de rota: cabeçalho + blocos, usado pelos `loading.tsx`. */
export function RouteLoading({ title, blocks = 3 }: { title: string; blocks?: number }) {
  return (
    <div role="status" aria-label={`Carregando ${title}`} className="stagger space-y-4">
      <div className="space-y-2" style={{ "--i": 0 } as React.CSSProperties}>
        <Skeleton className="h-6 w-48" />
        <Skeleton className="h-4 w-80 max-w-full" />
      </div>
      {Array.from({ length: blocks }, (_, i) => (
        <Skeleton key={i} className="h-36" style={{ "--i": i + 1 } as React.CSSProperties} />
      ))}
    </div>
  );
}

/** Erro de rota: mostra o que quebrou, oferece `reset` e um caminho de volta. Usado pelos `error.tsx`. */
export function RouteError({ title, error, reset }: { title: string; error: Error & { digest?: string }; reset: () => void }) {
  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold tracking-tight">{title}</h2>
      <ErrorState title="Esta tela falhou ao renderizar" error={error.digest ? `${error.message} (ref. ${error.digest})` : error} onRetry={reset} retryLabel="Recarregar a tela" />
      <Button asChild variant="outline" size="sm">
        <Link href="/">Voltar à visão geral</Link>
      </Button>
    </div>
  );
}
