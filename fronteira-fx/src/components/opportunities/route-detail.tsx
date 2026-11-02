"use client";
import type { Opportunity } from "@/lib/api/types";
import { CITY_LABEL, MODALITY_LABEL } from "@/lib/api/types";
import { formatDateTime, formatFee, formatMoney, formatPercent } from "@/lib/format";
import { formatRateFixed } from "@/components/ui/rate";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { ConfidenceBadge } from "./ranking-table";
import Link from "next/link";
import { MODE_LABEL } from "@/components/ui/labels";

function place(loc: string) {
  return loc === "digital" ? "Digital" : (CITY_LABEL as Record<string, string>)[loc] ?? loc;
}


export function RouteDetail({ opportunity: o, onClose }: { opportunity: Opportunity | null; onClose: () => void }) {
  const incomplete = o?.confidence === "incomplete";
  return (
    <Dialog open={!!o} onOpenChange={(v) => !v && onClose()}>
      <DialogContent>
        {o && (
          <>
            <DialogHeader>
              <DialogTitle>{o.title}</DialogTitle>
              <DialogDescription>
                {o.channel === "digital" ? "Operação digital" : `Presencial · ${o.city ? CITY_LABEL[o.city] : ""}`} · calculado em {formatDateTime(o.computed_at)} · {MODE_LABEL[o.data_mode]}
              </DialogDescription>
            </DialogHeader>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <Kpi label="Capital alocado" value={formatMoney(o.capital_brl, "BRL")} />
              <Kpi label="Valor final" value={formatMoney(o.final_value_brl, o.valuation_currency)} />
              <Kpi label="Ganho líquido" value={`${incomplete ? "≈ " : ""}${formatMoney(o.net_gain_brl, o.valuation_currency, { sign: !incomplete })}`} tone={incomplete ? "muted" : Number(o.net_gain_brl) >= 0 ? "gain" : "loss"} />
              <Kpi label="ROI" value={`${incomplete ? "≈ " : ""}${formatPercent(o.roi, { sign: !incomplete })}`} tone={incomplete ? "muted" : Number(o.roi) >= 0 ? "gain" : "loss"} />
            </div>
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <ConfidenceBadge c={o.confidence} />
              <Badge variant={o.in_main_ranking ? "accent" : "outline"}>{o.in_main_ranking ? "Ranking principal" : "Ranking secundário"}</Badge>
              <span className="text-muted">{o.ranking_reason}</span>
            </div>
            {o.pending_costs.length > 0 && (
              <div className="rounded-md border border-dashed border-warn/60 bg-warn/10 p-3 text-xs">
                <p className="font-medium text-warn">Custos pendentes — ganho não confirmado</p>
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
                    <Row k="Taxa" v={s.rate ? `${formatRateFixed(s.rate, s.to.currency, { decimals: s.to.currency === "PYG" ? 2 : 4 })} ${s.to.currency} por 1 ${s.from.currency} (${s.rate_note})` : "—"} />
                    <Row k="Custos" v={s.fees.length ? s.fees.map(formatFee).join("; ") : "nenhum conhecido"} />
                    <Row k="Prazo" v={s.duration} />
                    <Row k="Promoção" v={s.promo ?? "—"} />
                    <Row k="Contas" v={[s.from.account_id, s.to.account_id].filter(Boolean).join(" → ") || "—"} />
                    <Row k="Evidência" v={s.evidence_id ? <Link className="text-accent underline" href={`/fontes?evidence=${encodeURIComponent(s.evidence_id)}`}>{s.evidence_id}</Link> : "—"} />
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

function Kpi({ label, value, tone }: { label: string; value: string; tone?: "gain" | "loss" | "muted" }) {
  return (
    <div className="rounded-md border border-border p-2.5">
      <p className="text-xs text-muted">{label}</p>
      <p className={`tnum text-base font-semibold ${tone === "gain" ? "text-gain" : tone === "loss" ? "text-loss" : tone === "muted" ? "text-muted" : ""}`}>{value}</p>
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
