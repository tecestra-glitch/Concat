"use client";
import * as React from "react";
import { useAccounts } from "@/lib/queries";
import { PageHeader } from "@/components/shell/page-header";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { formatAge, formatMoney } from "@/lib/format";
import { CITY_LABEL, type Account } from "@/lib/api/types";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input, Label } from "@/components/ui/input";
import { useSettings } from "@/lib/settings";

const KIND: Record<Account["kind"], string> = { bank: "Conta bancária", fintech: "Fintech", cash: "Dinheiro físico", card_debit: "Cartão de débito", card_credit: "Cartão de crédito", card_virtual: "Cartão virtual" };

export function Accounts() {
  const q = useAccounts();
  const { mode } = useSettings();
  const [local, setLocal] = React.useState<Account[]>([]);
  const accounts = [...(q.data ?? []), ...local];
  const byInstitution = accounts.reduce<Record<string, Account[]>>((acc, a) => ((acc[a.institution] ??= []).push(a), acc), {});
  return (
    <div className="space-y-4">
      <PageHeader title="Contas e cartões" description="Saldos informados manualmente até a conexão das contas. Débito, crédito e cartão virtual são tratados separadamente.">
        <NewAccountDialog onCreate={(a) => setLocal((l) => [...l, a])} />
      </PageHeader>
      {mode === "demo" && <p className="text-xs text-warn">Conexão de contas e movimentações financeiras serão habilitadas em fase posterior; nada aqui executa operações.</p>}
      {q.isLoading && <Skeleton className="h-40" />}
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {Object.entries(byInstitution).map(([inst, list]) => (
          <Card key={inst}>
            <CardHeader><CardTitle>{inst}</CardTitle><CardDescription>{list.length} posição{list.length === 1 ? "" : "ões"}</CardDescription></CardHeader>
            <CardContent className="space-y-2">
              {list.map((a) => (
                <div key={a.id} className="rounded-md border border-border p-2.5 text-sm">
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <p className="font-medium">{a.label}</p>
                      <p className="text-xs text-muted">{KIND[a.kind]} · {a.location === "digital" ? "Digital" : CITY_LABEL[a.location]} · atualizado {formatAge(a.updated_at)}</p>
                    </div>
                    <Badge variant={a.kind.startsWith("card") ? "accent" : "outline"}>{a.currency}</Badge>
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
      <Card>
        <CardHeader><CardTitle>Cenário “Pagar uma compra” (cartão ueno)</CardTitle><CardDescription>Até validar a moeda efetivamente debitada e os encargos, o resultado é exibido como estimativa incompleta. O saldo USD não é presumido como usado automaticamente.</CardDescription></CardHeader>
        <CardContent className="grid gap-2 text-sm sm:grid-cols-3">
          <Scenario title="BRL → Western Union → saldo ueno → compra com cartão" items={["moeda da compra: PYG", "conta debitada: ueno PYG", "conversão: não (saldo PYG)", "tarifas: pendentes", "benefícios elegíveis: a confirmar"]} />
          <Scenario title="Saldo ueno → conversão PYG/USD → compra" items={["moeda da compra: USD", "conta debitada: ueno USD", "conversão: ueno venda USD", "tarifas: pendentes", "lançamento final: estimado"]} />
          <Scenario title="Saldo ueno → pagamento de fatura de crédito" items={["cartão: crédito", "fatura em PYG", "pagamento: saldo PYG", "juros/encargos: pendentes", "cálculo da fatura incluído"]} />
        </CardContent>
      </Card>
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
      <Badge variant="loss" className="mt-2">Estimativa incompleta</Badge>
    </div>
  );
}

function NewAccountDialog({ onCreate }: { onCreate: (a: Account) => void }) {
  const [open, setOpen] = React.useState(false);
  const [form, setForm] = React.useState({ institution: "", label: "", currency: "USD", kind: "bank", location: "digital", balance_free: "0" });
  const valid = form.institution.trim() && form.label.trim() && Number.isFinite(Number(form.balance_free));
  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!valid) return;
    onCreate({ id: `local-${Date.now()}`, institution: form.institution.trim(), label: form.label.trim(), currency: form.currency as Account["currency"], kind: form.kind as Account["kind"], location: form.location as Account["location"], balance_free: form.balance_free, balance_reserved: "0", balance_in_transit: "0", updated_at: new Date().toISOString() });
    setOpen(false);
  };
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild><Button size="sm">Cadastrar conta</Button></DialogTrigger>
      <DialogContent className="max-w-md">
        <DialogHeader><DialogTitle>Nova conta ou cartão</DialogTitle><DialogDescription>Cadastro extensível de instituições, contas e moedas. Em modo demonstração o registro fica apenas nesta sessão.</DialogDescription></DialogHeader>
        <form onSubmit={submit} className="grid gap-3">
          <div className="grid gap-1"><Label htmlFor="inst">Instituição</Label><Input id="inst" value={form.institution} onChange={(e) => setForm({ ...form, institution: e.target.value })} required /></div>
          <div className="grid gap-1"><Label htmlFor="label">Rótulo</Label><Input id="label" value={form.label} onChange={(e) => setForm({ ...form, label: e.target.value })} required /></div>
          <div className="grid grid-cols-3 gap-2">
            <div className="grid gap-1"><Label htmlFor="cur">Moeda</Label><select id="cur" className="h-9 rounded-md border border-border bg-background px-2 text-sm" value={form.currency} onChange={(e) => setForm({ ...form, currency: e.target.value })}><option>BRL</option><option>USD</option><option>PYG</option></select></div>
            <div className="grid gap-1"><Label htmlFor="kind">Tipo</Label><select id="kind" className="h-9 rounded-md border border-border bg-background px-2 text-sm" value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}>{Object.entries(KIND).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></div>
            <div className="grid gap-1"><Label htmlFor="loc">Local</Label><select id="loc" className="h-9 rounded-md border border-border bg-background px-2 text-sm" value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })}><option value="digital">Digital</option><option value="CDE">CDE</option><option value="ASU">ASU</option><option value="PJC">PJC</option></select></div>
          </div>
          <div className="grid gap-1"><Label htmlFor="bal">Saldo livre</Label><Input id="bal" inputMode="decimal" value={form.balance_free} onChange={(e) => setForm({ ...form, balance_free: e.target.value })} /></div>
          <Button type="submit" disabled={!valid}>Salvar</Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
