"use client";
/**
 * Peças comuns das telas do triangulador. Todo número passa por `Tag` (executável ou referência) e por `SourceLine`
 * (fonte e data), para nunca aparecer solto. Nenhuma peça aqui envia ordem.
 */
import * as React from "react";
import { Badge } from "@/components/ui/badge";
import { EXECUTABLE_LABEL, REFERENCE_LABEL } from "@/lib/api/triangulador";
import { formatDateTime } from "@/lib/format";

/** Selo do rótulo. `executable=false` sempre mostra «Referência · não executável» com contorno tracejado. */
export function Tag({ executable }: { executable: boolean }) {
  return executable ? (
    <Badge variant="gain" data-testid="tag-executable">{EXECUTABLE_LABEL}</Badge>
  ) : (
    <Badge variant="reference" data-testid="tag-reference">{REFERENCE_LABEL}</Badge>
  );
}

/** Fonte e data observada, sempre visíveis ao lado de cada número. */
export function SourceLine({ source, at, label = "Observado" }: { source: string; at: string | null | undefined; label?: string }) {
  return (
    <p className="break-words text-xs text-muted">
      Fonte: <span className="text-foreground">{source}</span> · {label} {at ? formatDateTime(at) : "sem data"}
    </p>
  );
}

/** Lista de cartões em uma grade que quebra em 1 coluna no celular (sem rolagem horizontal). */
export function CardGrid({ children, label }: { children: React.ReactNode; label: string }) {
  return (
    <ul aria-label={label} className="grid min-w-0 gap-3 sm:grid-cols-2 xl:grid-cols-3">
      {children}
    </ul>
  );
}

export function Notice({ children }: { children: React.ReactNode }) {
  return <p className="rounded-control border border-border bg-surface-2 px-3 py-2 text-xs text-muted">{children}</p>;
}
