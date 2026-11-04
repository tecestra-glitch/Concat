"use client";
import { useRouter } from "next/navigation";
import { TriangleAlert } from "lucide-react";
import type { Cycle } from "@/lib/api/types";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { formatMoney, formatPercent } from "@/lib/format";
import { useCreatePlan } from "@/lib/queries";
import { ConfidenceBadge } from "./ranking-table";
import { LegChannel } from "./leg-channel";
import { CHANNEL_TEXT, CYCLE_CURRENCIES, NEEDS_DECLARATION_USD, costRows, cycleCurrency, cycleGain, formatMinutes, isProfitable, legLabel, legText, pathLabel } from "./cycle-helpers";

/** Detalhe de um ciclo: pernas com canal, quebra de custos, ganho por moeda e o aviso de declaração. */
export function CycleDetail({ cycle: c, onClose }: { cycle: Cycle | null; onClose: () => void }) {
  const router = useRouter();
  const plan = useCreatePlan();
  const currency = c ? cycleCurrency(c.start) : "BRL";
  const incomplete = c?.confidence === "incomplete";
  const unknownCosts = c ? costRows(c, currency).filter((r) => r.value === null).map((r) => r.label) : [];
  const onPlan = async () => {
    if (!c) return;
    const p = await plan.mutateAsync({ start: c.start, path: c.path });
    router.push(`/planos/${p.id}`);
  };
  return (
    <Dialog open={!!c} onOpenChange={(v) => !v && onClose()}>
      <DialogContent>
        {c && (
          <>
            <DialogHeader>
              <DialogTitle>Ciclo a partir de {c.start}</DialogTitle>
              <DialogDescription>
                {c.legs.length} perna{c.legs.length === 1 ? "" : "s"} · {formatMinutes(c.minutes)} no total · calculado sobre {formatMoney(c.amount_in, currency)}
              </DialogDescription>
            </DialogHeader>

            <p className="break-words text-xs text-muted" data-testid="cycle-path">Caminho: {pathLabel(c.path)}</p>

            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <Kpi label={`Ganho em ${currency}`} value={`${incomplete ? "≈ " : ""}${formatMoney(c.gain, currency, { sign: !incomplete })}`} tone={incomplete ? "muted" : isProfitable(c) ? "gain" : "loss"} strong />
              <Kpi label="ROI" value={`${incomplete ? "≈ " : ""}${formatPercent(c.roi, { sign: !incomplete })}`} tone={incomplete ? "muted" : isProfitable(c) ? "gain" : "loss"} />
              <Kpi label="Saída" value={formatMoney(c.amount_out, currency)} />
              <div className="flex flex-col items-start justify-center gap-1 rounded-md border border-border p-2.5">
                <p className="text-xs text-muted">Confiança</p>
                <ConfidenceBadge c={c.confidence} />
              </div>
            </div>

            <section aria-labelledby="gains-title" className="space-y-1">
              <h3 id="gains-title" className="text-sm font-semibold">Ganho líquido nas três moedas</h3>
              <ul className="grid grid-cols-3 gap-2 text-sm" data-testid="gain-by-currency">
                {CYCLE_CURRENCIES.map((cur) => {
                  const v = cycleGain(c, cur);
                  return (
                    <li key={cur} className={`rounded-md border p-2 ${cur === currency ? "border-accent/60 bg-accent/10" : "border-border"}`} data-currency={cur} data-highlight={cur === currency}>
                      <p className="text-xs text-muted">{cur === currency ? `${cur} (moeda de partida)` : cur}</p>
                      <p className="tnum font-semibold">{v === null ? "não convertido" : `${incomplete ? "≈ " : ""}${formatMoney(v, cur, { sign: !incomplete })}`}</p>
                    </li>
                  );
                })}
              </ul>
            </section>

            {c.requires_declaration && (
              <div role="note" className="flex gap-2 rounded-md border border-warn/60 bg-warn/10 p-3 text-xs" data-testid="declaration-warning">
                <TriangleAlert className="mt-0.5 size-4 shrink-0 text-warn" aria-hidden />
                <p>
                  <span className="font-medium text-warn">Declaração: </span>
                  uma perna de fronteira passa de US$ {NEEDS_DECLARATION_USD.toLocaleString("pt-BR")}. Confira antes de atravessar a fronteira. Isto é um aviso e não bloqueia o plano.
                </p>
              </div>
            )}

            {unknownCosts.length > 0 && (
              <div className="rounded-md border border-dashed border-warn/60 bg-warn/10 p-3 text-xs" data-testid="unknown-costs">
                <p className="font-medium text-warn">Custos não informados: {unknownCosts.join(", ").toLowerCase()}</p>
                <p className="mt-1 text-foreground/80">Um custo desconhecido não vira zero. O ganho aparece como estimativa, sem confirmação.</p>
              </div>
            )}

            <section aria-labelledby="costs-title" className="space-y-1">
              <h3 id="costs-title" className="text-sm font-semibold">Quebra de custos em {currency}</h3>
              <dl className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-4" data-testid="cost-rows">
                {costRows(c, currency).map((r) => (
                  <div key={r.label} className="rounded-md border border-border p-2">
                    <dt className="text-xs text-muted">{r.label}</dt>
                    <dd className={`tnum ${r.value === null ? "text-muted" : ""}`}>{r.value ?? "não informado"}</dd>
                  </div>
                ))}
              </dl>
            </section>

            <section aria-labelledby="legs-title" className="space-y-2">
              <h3 id="legs-title" className="text-sm font-semibold">Pernas, na ordem</h3>
              <ol className="space-y-2">
                {c.legs.map((leg, i) => (
                  <li key={i} className="rounded-md border border-border bg-surface-2/60 p-3 text-sm" data-testid="leg">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="tnum text-muted">{i + 1}.</span>
                      <span className="font-medium">{legLabel(leg.kind, leg.channel)}</span>
                      <LegChannel channel={leg.channel} />
                      {leg.border && <Badge variant="warn">cruza a fronteira</Badge>}
                    </div>
                    <p className="mt-1 text-xs text-muted">{legText(leg)} · {formatMinutes(leg.minutes)}</p>
                    <p className="mt-1 text-xs text-muted">{CHANNEL_TEXT[leg.channel]}</p>
                  </li>
                ))}
              </ol>
            </section>

            <div className="flex flex-col gap-2 border-t border-border pt-3 sm:flex-row sm:items-center sm:justify-between">
              <p className="text-xs text-muted">Gerar o plano não executa nada: ele só organiza os passos para você seguir.</p>
              <Button onClick={() => void onPlan()} disabled={!isProfitable(c) || plan.isPending} title={isProfitable(c) ? undefined : "Só ciclos com ganho líquido positivo viram plano"}>
                {plan.isPending ? "Gerando plano…" : "Gerar plano"}
              </Button>
            </div>
            {plan.isError && <p role="alert" className="text-xs text-loss">Não foi possível gerar o plano: {plan.error instanceof Error ? plan.error.message : "erro"}</p>}
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

function Kpi({ label, value, tone, strong }: { label: string; value: string; tone?: "gain" | "loss" | "muted"; strong?: boolean }) {
  const color = tone === "gain" ? "text-gain" : tone === "loss" ? "text-loss" : tone === "muted" ? "text-muted" : "";
  return (
    <div className="rounded-md border border-border p-2.5">
      <p className="text-xs text-muted">{label}</p>
      <p className={`tnum ${strong ? "text-lg" : "text-base"} font-semibold ${color}`}>{value}</p>
    </div>
  );
}

