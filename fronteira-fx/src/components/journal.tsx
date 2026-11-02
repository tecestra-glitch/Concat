"use client";
import * as React from "react";
import { useJournal } from "@/lib/queries";
import { PageHeader } from "@/components/shell/page-header";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { formatDateTime, formatMoney } from "@/lib/format";
import type { JournalEntry } from "@/lib/api/types";
import { Input, Label } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

const KIND: Record<JournalEntry["kind"], { label: string; v: "default" | "accent" | "gain" }> = { note: { label: "Nota", v: "default" }, operation: { label: "Operação", v: "accent" }, reconciliation: { label: "Reconciliação", v: "gain" } };

export function Journal() {
  const q = useJournal();
  const [local, setLocal] = React.useState<JournalEntry[]>([]);
  const [text, setText] = React.useState("");
  const entries = [...local, ...(q.data ?? [])].sort((a, b) => b.ts.localeCompare(a.ts));
  const add = (e: React.FormEvent) => {
    e.preventDefault();
    if (!text.trim()) return;
    setLocal((l) => [{ id: `local-${Date.now()}`, ts: new Date().toISOString(), kind: "note", text: text.trim(), amounts: [], account_ids: [] }, ...l]);
    setText("");
  };
  return (
    <div className="space-y-4">
      <PageHeader title="Diário de operações" description="Registro de simulações, operações aprovadas e reconciliações. Nada aqui executa movimentações." />
      <Card>
        <CardContent className="pt-4">
          <form onSubmit={add} className="flex flex-col gap-2 sm:flex-row sm:items-end">
            <div className="grid flex-1 gap-1"><Label htmlFor="nota">Nova nota</Label><Input id="nota" value={text} onChange={(e) => setText(e.target.value)} placeholder="Ex.: conferi saldo ueno no app" /></div>
            <Button type="submit" disabled={!text.trim()}>Registrar</Button>
          </form>
        </CardContent>
      </Card>
      {q.isLoading && <Skeleton className="h-32" />}
      <ol className="space-y-2">
        {entries.map((e) => (
          <li key={e.id} className="rounded-md border border-border bg-surface p-3 text-sm">
            <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
              <Badge variant={KIND[e.kind].v}>{KIND[e.kind].label}</Badge>
              <span className="tnum">{formatDateTime(e.ts)}</span>
              {e.account_ids.length > 0 && <span>· {e.account_ids.join(", ")}</span>}
            </div>
            <p className="mt-1">{e.text}</p>
            {e.amounts.length > 0 && <p className="tnum mt-1 text-xs text-muted">{e.amounts.map((a) => `${a.label}: ${formatMoney(a.amount, a.currency)}`).join(" · ")}</p>}
          </li>
        ))}
      </ol>
    </div>
  );
}
