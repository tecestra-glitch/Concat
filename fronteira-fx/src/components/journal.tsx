"use client";
import * as React from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useJournal } from "@/lib/queries";
import { api } from "@/lib/api/client";
import { useSettings } from "@/lib/settings";
import { PageHeader } from "@/components/shell/page-header";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { formatDateTime, formatFee } from "@/lib/format";
import type { JournalEntry } from "@/lib/api/types";
import { Input, Label } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { TableSkeleton } from "@/components/ui/table-skeleton";
import { ErrorState } from "@/components/ui/error-state";
import { EmptyState } from "@/components/ui/empty-state";
import { MODE_LABEL, MODE_TONE } from "@/components/ui/labels";

const KIND: Record<JournalEntry["kind"], { label: string; v: "default" | "accent" | "gain" }> = { note: { label: "Nota", v: "default" }, operation: { label: "Operação", v: "accent" }, reconciliation: { label: "Reconciliação", v: "gain" }, result: { label: "Resultado de plano", v: "accent" } };

export function Journal() {
  const { mode } = useSettings();
  const q = useJournal();
  const qc = useQueryClient();
  const [text, setText] = React.useState("");
  const create = useMutation({
    mutationFn: (t: string) => api.createJournal(mode, { kind: "note", text: t, amounts: [], account_ids: [] }),
    onSuccess: () => {
      setText("");
      void qc.invalidateQueries({ queryKey: ["journal", mode] });
    },
  });
  const entries = React.useMemo(() => [...(q.data ?? [])].sort((a, b) => b.ts.localeCompare(a.ts)), [q.data]);
  const add = (e: React.FormEvent) => {
    e.preventDefault();
    const t = text.trim();
    if (!t || create.isPending) return;
    create.mutate(t);
  };
  return (
    <div className="space-y-4">
      <PageHeader title="Diário de operações" description="Registro de simulações, operações aprovadas e reconciliações. Nada aqui executa movimentações.">
        <Badge variant={MODE_TONE[mode]} data-testid="journal-mode">{MODE_LABEL[mode]}</Badge>
      </PageHeader>
      <Card>
        <CardContent className="pt-4">
          <form onSubmit={add} className="flex flex-col gap-2 sm:flex-row sm:items-end">
            <div className="grid flex-1 gap-1"><Label htmlFor="nota">Nova nota</Label><Input id="nota" value={text} onChange={(e) => setText(e.target.value)} placeholder="Ex.: conferi saldo ueno no app" disabled={create.isPending} /></div>
            <Button type="submit" disabled={!text.trim() || create.isPending}>{create.isPending ? "Registrando…" : "Registrar"}</Button>
          </form>
          {create.isError && <p role="alert" className="mt-2 text-xs text-loss" data-testid="journal-error">Não foi possível registrar a nota: {(create.error as Error).message}</p>}
          {mode === "demo" && <p className="mt-2 text-xs text-muted">Demonstração: a nota fica só nesta sessão, marcada como demonstração.</p>}
        </CardContent>
      </Card>
      {q.isLoading && <TableSkeleton rows={4} cols={2} />}
      {q.isError && <ErrorState title="O diário não carregou" error={q.error} onRetry={() => void q.refetch()} />}
      {q.data && entries.length === 0 && <EmptyState kind="no-data" title="Diário vazio" description="Registre a primeira nota acima; simulações aprovadas e reconciliações entram aqui automaticamente." />}
      <ol className="space-y-2" aria-label="Entradas do diário">
        {entries.map((e) => (
          <li key={e.id} className="rounded-md border border-border bg-surface p-3 text-sm" data-testid="journal-entry">
            <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
              <Badge variant={KIND[e.kind].v}>{KIND[e.kind].label}</Badge>
              <time dateTime={e.ts} className="tnum">{formatDateTime(e.ts)}</time>
              {e.account_ids.length > 0 && <span>· {e.account_ids.join(", ")}</span>}
              {mode === "demo" && <Badge variant="warn">demonstração</Badge>}
            </div>
            <p className="mt-1">{e.text}</p>
            {e.amounts.length > 0 && <p className="tnum mt-1 text-xs text-muted">{e.amounts.map(formatFee).join(" · ")}</p>}
          </li>
        ))}
      </ol>
    </div>
  );
}
