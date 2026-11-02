"use client";
import type { Opportunity } from "@/lib/api/types";
import { CITY_LABEL, MODALITY_LABEL } from "@/lib/api/types";
import { formatDateTime, formatMoney, formatPercent } from "@/lib/format";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { ConfidenceBadge } from "./ranking-table";
import Link from "next/link";

function place(loc: string) {
  return loc === "digital" ? "Digital" : (CITY_LABEL as Record<string, string>)[loc] ?? loc;
}

export function RouteDetail({ opportunity: o, onClose }: { opportunity: Opportunity | null; onClose: () => void }) {
  return (
    <Dialog open={!!o} onOpenChange={(v) => !v && onClose()}>
      <DialogContent>
        {o && (
          <>
            <DialogHeader>
              <DialogTitle>{o.title}</DialogTitle>
              <DialogDescription>
                {o.channel === "digital" ? "Operação digital" : `Presencial · ${o.city ? CITY_LABEL[o.city] : ""}`} · calculado em {formatDateTime(o.computed_at)} · {o.data_mode === "demo" ? "DEMONSTRAÇÃO" : o.data_mode}
              </DialogDescription>
            </DialogHeader>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <Kpi label="Capital alocado" value={formatMoney(o.capital_brl, "BRL")} />
              <Kpi label="Valor final" value={formatMoney(o.final_value_brl, o.valuation_currency)} />
              <Kpi label="Ganho líquido" value={formatMoney(o.net_gain_brl, o.valuation_currency, { sign: true })} tone={Number(o.net_gain_brl) >= 0 ? "gain" : "loss"} />
              <Kpi label="ROI" value={formatPercent(o.roi, { sign: true })} tone={Number(o.roi) >= 0 ? "gain" : "loss"} />
            </div>
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <ConfidenceBadge c={o.confidence} />
              <Badge variant={o.in_main_ranking ? "accent" : "outline"}>{o.in_main_ranking ? "Ranking principal" : "Ranking secundário"}</Badge>
              <span className="text-muted">{o.ranking_reason}</span>
            </div>
            {o.pending_costs.length > 0 && (
              <div className="rounded-md border border-loss/40 bg-loss/10 p-3 text-xs">
                <p className="font-medium text-loss">Custos pendentes — lucro líquido não confirmado</p>
                <ul className="mt-1 list-disc pl-4 text-foreground/80">{o.pending_costs.map((p) => <li key={p}>{p}</li>)}</ul>
              </div>
            )}
            <ol className="space-y-2">
              {o.steps.map((s) => (
                <li key={s.n} className="rounded-md border border-border bg-surface-2/60 p-3 text-sm">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <p className="font-medium"><span className="tnum text-muted">{s.n}.</span> {s.description}</p>
                    <ConfidenceBadge c={s.confidence} />
                  </div>
                  <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-xs sm:grid-cols-3">
                    <Row k="De" v={`${formatMoney(s.amount_in, s.from.currency)} · ${place(s.from.location)} · ${MODALITY_LABEL[s.from.modality]}`} />
                    <Row k="Para" v={`${formatMoney(s.amount_out, s.to.currency)} · ${place(s.to.location)} · ${MODALITY_LABEL[s.to.modality]}`} />
                    <Row k="Taxa" v={s.rate ? `${Number(s.rate).toLocaleString("pt-BR", { maximumFractionDigits: 6 })} (${s.rate_note})` : "—"} />
                    <Row k="Custos" v={s.fees.length ? s.fees.map((f) => `${f.label}: ${formatMoney(f.amount, f.currency)}`).join("; ") : "nenhum conhecido"} />
                    <Row k="Prazo" v={s.duration} />
                    <Row k="Promoção" v={s.promo ?? "—"} />
                    <Row k="Contas" v={[s.from.account_id, s.to.account_id].filter(Boolean).join(" → ") || "—"} />
                    <Row k="Evidência" v={s.evidence_id ? <Link className="text-accent underline" href={`/fontes?evidence=${s.evidence_id}`}>{s.evidence_id}</Link> : "—"} />
                  </dl>
                </li>
              ))}
            </ol>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

function Kpi({ label, value, tone }: { label: string; value: string; tone?: "gain" | "loss" }) {
  return (
    <div className="rounded-md border border-border p-2.5">
      <p className="text-[11px] uppercase tracking-wide text-muted">{label}</p>
      <p className={`tnum text-base font-semibold ${tone === "gain" ? "text-gain" : tone === "loss" ? "text-loss" : ""}`}>{value}</p>
    </div>
  );
}
function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-muted">{k}</dt>
      <dd className="truncate" title={typeof v === "string" ? v : undefined}>{v}</dd>
    </div>
  );
}
