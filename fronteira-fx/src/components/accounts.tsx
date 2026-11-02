"use client";
import * as React from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Pencil } from "lucide-react";
import { useAccounts } from "@/lib/queries";
import { api } from "@/lib/api/client";
import { PageHeader } from "@/components/shell/page-header";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { formatAge, formatMoney, parseDecimalPtBR } from "@/lib/format";
import { CITY_LABEL, type Account, type AccountPatch } from "@/lib/api/types";
import { TableSkeleton } from "@/components/ui/table-skeleton";
import { ErrorState } from "@/components/ui/error-state";
import { EmptyState } from "@/components/ui/empty-state";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input, Label } from "@/components/ui/input";
import { useSettings } from "@/lib/settings";
import { useNow } from "@/lib/use-now";
import { accountInputFromForm, canonicalToPtBR, EMPTY_ACCOUNT_FORM, validateAccountForm, type AccountForm } from "./accounts-form";
import { useSubmitState } from "@/components/ui/use-submit";

const KIND: Record<Account["kind"], string> = { bank: "Conta bancária", fintech: "Fintech", cash: "Dinheiro físico", card_debit: "Cartão de débito", card_credit: "Cartão de crédito", card_virtual: "Cartão virtual" };

export function Accounts() {
  const q = useAccounts();
  const { mode } = useSettings();
  const now = useNow();
  const qc = useQueryClient();
  const invalidate = () => qc.invalidateQueries({ queryKey: ["accounts", mode] });
  const create = useMutation({ mutationFn: (f: AccountForm) => api.createAccount(mode, accountInputFromForm(f)), onSuccess: invalidate });
  const update = useMutation({ mutationFn: ({ id, patch }: { id: string; patch: AccountPatch }) => api.updateAccount(mode, id, patch), onSuccess: invalidate });
  const accounts = q.data ?? [];
  const byInstitution = accounts.reduce<Record<string, Account[]>>((acc, a) => ((acc[a.institution] ??= []).push(a), acc), {});
  return (
    <div className="space-y-4">
      <PageHeader title="Contas e cartões" description="Saldos informados manualmente até a conexão das contas. Débito, crédito e cartão virtual são tratados separadamente.">
        <NewAccountDialog onCreate={(f) => create.mutateAsync(f)} />
      </PageHeader>
      <p role="note" className="text-xs text-warn" data-testid="accounts-note">
        Nada aqui executa operações: conexão de contas e movimentações financeiras ficam para uma fase posterior, começando por aprovação manual.
        {mode === "demo" && " Em demonstração, os registros vivem só nesta sessão."}
      </p>
      {q.isLoading && <TableSkeleton rows={4} cols={3} />}
      {q.isError && <ErrorState title="As contas não carregaram" error={q.error} onRetry={() => void q.refetch()} />}
      {q.data && accounts.length === 0 && <EmptyState kind="no-data" title="Nenhuma conta cadastrada" description="Cadastre a primeira conta ou cartão para o grafo de posições ter de onde partir." />}
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3" data-testid="accounts-grid">
        {Object.entries(byInstitution).map(([inst, list]) => (
          <Card key={inst}>
            <CardHeader><CardTitle>{inst}</CardTitle><CardDescription>{list.length} posição{list.length === 1 ? "" : "ões"}</CardDescription></CardHeader>
            <CardContent className="space-y-2">
              {list.map((a) => (
                <div key={a.id} className="rounded-md border border-border p-2.5 text-sm" data-testid="account-card">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="font-medium">{a.label}</p>
                      <p className="text-xs text-muted">
                        {KIND[a.kind]} · {a.location === "digital" ? "Digital" : CITY_LABEL[a.location]} · atualizado <span data-volatile>{now === 0 ? "…" : formatAge(a.updated_at, now)}</span>
                        {mode === "demo" && a.id.startsWith("local-") && <> · <Badge variant="warn">só nesta sessão</Badge></>}
                      </p>
                    </div>
                    <div className="flex items-center gap-1">
                      <Badge variant={a.kind.startsWith("card") ? "accent" : "outline"}>{a.currency}</Badge>
                      <EditAccountDialog account={a} onSave={(patch) => update.mutateAsync({ id: a.id, patch })} />
                    </div>
                  </div>
                  <dl className="mt-2 grid grid-cols-3 gap-2 text-xs">
                    <Bal k="Livre" v={formatMoney(a.balance_free, a.currency)} />
                    <Bal k="Reservado" v={formatMoney(a.balance_reserved, a.currency)} />
                    <Bal k="Em trânsito" v={formatMoney(a.balance_in_transit, a.currency)} />
                  </dl>
                </div>
              ))}
            </CardContent>
          </Card>
        ))}
      </div>
      {mode === "demo" && (
        <Card>
          <CardHeader><CardTitle>Cenário “Pagar uma compra” (cartão ueno) — demonstração</CardTitle><CardDescription>Até validar a moeda efetivamente debitada e os encargos, o resultado é exibido como estimativa incompleta. O saldo USD não é presumido como usado automaticamente.</CardDescription></CardHeader>
          <CardContent className="grid gap-2 text-sm sm:grid-cols-3">
            <Scenario title="BRL → Western Union → saldo ueno → compra com cartão" items={["moeda da compra: PYG", "conta debitada: ueno PYG", "conversão: não (saldo PYG)", "tarifas: pendentes", "benefícios elegíveis: a confirmar"]} />
            <Scenario title="Saldo ueno → conversão PYG/USD → compra" items={["moeda da compra: USD", "conta debitada: ueno USD", "conversão: ueno venda USD", "tarifas: pendentes", "lançamento final: estimado"]} />
            <Scenario title="Saldo ueno → pagamento de fatura de crédito" items={["cartão: crédito", "fatura em PYG", "pagamento: saldo PYG", "juros/encargos: pendentes", "cálculo da fatura incluído"]} />
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function Bal({ k, v }: { k: string; v: string }) {
  return <div><dt className="text-muted">{k}</dt><dd className="tnum">{v}</dd></div>;
}
function Scenario({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="rounded-md border border-border p-3">
      <p className="font-medium">{title}</p>
      <ul className="mt-2 list-disc pl-4 text-xs text-muted">{items.map((i) => <li key={i}>{i}</li>)}</ul>
      <Badge variant="incomplete" className="mt-2"><span aria-hidden>?</span> Custo desconhecido</Badge>
    </div>
  );
}

const SELECT_CLASS = "h-9 rounded-md border border-border bg-background px-2 text-sm";

/** Fecha só depois do resultado: em erro o que foi digitado continua no diálogo. */
function NewAccountDialog({ onCreate }: { onCreate: (f: AccountForm) => Promise<unknown> }) {
  const [open, setOpen] = React.useState(false);
  const [form, setForm] = React.useState<AccountForm>(EMPTY_ACCOUNT_FORM);
  const { pending, error, run, clear } = useSubmitState();
  const [touched, setTouched] = React.useState(false);
  const validation = validateAccountForm(form);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setTouched(true);
    if (validation) return;
    if (await run(() => onCreate(form), "Falha ao salvar a conta.")) {
      setOpen(false);
      setForm(EMPTY_ACCOUNT_FORM);
      setTouched(false);
    }
  };
  return (
    <Dialog open={open} onOpenChange={(v) => { setOpen(v); if (!v) { clear(); setTouched(false); } }}>
      <DialogTrigger asChild><Button size="sm">Cadastrar conta</Button></DialogTrigger>
      <DialogContent className="max-w-md">
        <DialogHeader><DialogTitle>Nova conta ou cartão</DialogTitle><DialogDescription>Instituição, conta e moeda. O saldo é guardado como texto decimal, sem arredondar.</DialogDescription></DialogHeader>
        <form onSubmit={submit} className="grid gap-3" noValidate>
          <div className="grid gap-1"><Label htmlFor="inst">Instituição</Label><Input id="inst" value={form.institution} onChange={(e) => setForm({ ...form, institution: e.target.value })} required /></div>
          <div className="grid gap-1"><Label htmlFor="label">Rótulo</Label><Input id="label" value={form.label} onChange={(e) => setForm({ ...form, label: e.target.value })} required /></div>
          <div className="grid grid-cols-3 gap-2">
            <div className="grid gap-1"><Label htmlFor="cur">Moeda</Label><select id="cur" className={SELECT_CLASS} value={form.currency} onChange={(e) => setForm({ ...form, currency: e.target.value })}><option>BRL</option><option>USD</option><option>PYG</option></select></div>
            <div className="grid gap-1"><Label htmlFor="kind">Tipo</Label><select id="kind" className={SELECT_CLASS} value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}>{Object.entries(KIND).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></div>
            <div className="grid gap-1"><Label htmlFor="loc">Local</Label><select id="loc" className={SELECT_CLASS} value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })}><option value="digital">Digital</option><option value="CDE">CDE</option><option value="ASU">ASU</option><option value="PJC">PJC</option></select></div>
          </div>
          <div className="grid gap-1"><Label htmlFor="bal">Saldo livre</Label><Input id="bal" inputMode="decimal" value={form.balance_free} onChange={(e) => setForm({ ...form, balance_free: e.target.value })} aria-describedby="bal-help" aria-invalid={touched && !!validation} /><p id="bal-help" className="text-xs text-muted">Formato pt-BR: 5.000,50</p></div>
          {touched && validation && <p role="alert" className="text-xs text-loss">{validation}</p>}
          {error && <p role="alert" className="text-xs text-loss" data-testid="account-error">Não foi possível salvar: {error}</p>}
          <Button type="submit" disabled={pending || (touched && !!validation)}>{pending ? "Salvando…" : "Salvar"}</Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/** Os saldos da API são strings decimais canônicas; o campo é pt-BR, então a semente passa por `canonicalToPtBR`. */
function seedFrom(account: Account) {
  return { label: account.label, balance_free: canonicalToPtBR(account.balance_free), balance_reserved: canonicalToPtBR(account.balance_reserved), balance_in_transit: canonicalToPtBR(account.balance_in_transit) };
}

function EditAccountDialog({ account, onSave }: { account: Account; onSave: (patch: AccountPatch) => Promise<unknown> }) {
  const [open, setOpen] = React.useState(false);
  const [form, setForm] = React.useState(() => seedFrom(account));
  const { pending, error, run, clear } = useSubmitState();
  const parsed = { free: parseDecimalPtBR(form.balance_free), reserved: parseDecimalPtBR(form.balance_reserved), transit: parseDecimalPtBR(form.balance_in_transit) };
  const invalid = !form.label.trim() || parsed.free === null || parsed.reserved === null || parsed.transit === null;
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (invalid) return;
    if (await run(() => onSave({ label: form.label.trim(), balance_free: parsed.free!, balance_reserved: parsed.reserved!, balance_in_transit: parsed.transit! }))) setOpen(false);
  };
  return (
    <Dialog open={open} onOpenChange={(v) => { setOpen(v); if (v) { setForm(seedFrom(account)); clear(); } }}>
      <DialogTrigger asChild>
        <Button size="icon" variant="ghost" className="h-7 w-7" aria-label={`Editar ${account.label}`}><Pencil /></Button>
      </DialogTrigger>
      <DialogContent className="max-w-md">
        <DialogHeader><DialogTitle>Editar {account.label}</DialogTitle><DialogDescription>{account.institution} · {KIND[account.kind]} · {account.currency}</DialogDescription></DialogHeader>
        <form onSubmit={submit} className="grid gap-3" noValidate>
          <div className="grid gap-1"><Label htmlFor={`e-label-${account.id}`}>Rótulo</Label><Input id={`e-label-${account.id}`} value={form.label} onChange={(e) => setForm({ ...form, label: e.target.value })} /></div>
          <div className="grid grid-cols-3 gap-2">
            <div className="grid gap-1"><Label htmlFor={`e-free-${account.id}`}>Livre</Label><Input id={`e-free-${account.id}`} inputMode="decimal" value={form.balance_free} onChange={(e) => setForm({ ...form, balance_free: e.target.value })} aria-invalid={parsed.free === null} /></div>
            <div className="grid gap-1"><Label htmlFor={`e-res-${account.id}`}>Reservado</Label><Input id={`e-res-${account.id}`} inputMode="decimal" value={form.balance_reserved} onChange={(e) => setForm({ ...form, balance_reserved: e.target.value })} aria-invalid={parsed.reserved === null} /></div>
            <div className="grid gap-1"><Label htmlFor={`e-tr-${account.id}`}>Em trânsito</Label><Input id={`e-tr-${account.id}`} inputMode="decimal" value={form.balance_in_transit} onChange={(e) => setForm({ ...form, balance_in_transit: e.target.value })} aria-invalid={parsed.transit === null} /></div>
          </div>
          {invalid && <p role="alert" className="text-xs text-loss">Preencha o rótulo e saldos válidos (ex.: 5.000,50).</p>}
          {error && <p role="alert" className="text-xs text-loss">Não foi possível salvar: {error}</p>}
          <Button type="submit" disabled={pending || invalid}>{pending ? "Salvando…" : "Salvar alterações"}</Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
