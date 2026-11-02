"use client";
import * as React from "react";
import type { Confidence, Opportunity } from "@/lib/api/types";
import { CITY_LABEL } from "@/lib/api/types";
import { formatMoney, toNumber } from "@/lib/format";
import { formatRateFixed } from "@/components/ui/rate";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Delta } from "@/components/ui/delta";
import { EmptyState } from "@/components/ui/empty-state";
import { RouteDetail } from "./route-detail";

const KIND_LABEL: Record<Opportunity["kind"], string> = { cycle: "Lucro de ciclo", remittance_saving: "Economia em remessa", purchase_saving: "Economia em compra" };

/** Moeda da taxa efetiva: a do destino da última etapa (sem heurística por tipo). */
function rateCurrency(o: Opportunity) {
  return o.steps.at(-1)?.to.currency ?? o.valuation_currency;
}

/** `compact` (visão geral) esconde Canal, Tipo e Taxa efetiva; o detalhe da rota continua com tudo. */
export function RankingTable({ items, title, emptyText, compact = false }: { items: Opportunity[]; title?: string; emptyText?: string; compact?: boolean }) {
  const [open, setOpen] = React.useState<Opportunity | null>(null);
  return (
    <div>
      {title && <h3 className="mb-2 text-sm font-semibold">{title}</h3>}
      {items.length === 0 ? (
        <EmptyState kind="no-data" compact title={emptyText ?? "Nenhuma oportunidade"} description="O ranking vem do motor do backend; quando uma rota passar nos critérios, ela aparece aqui." />
      ) : (
        <Table scrollLabel="Ranking de oportunidades (rola para o lado)">
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead>#</TableHead>
              <TableHead>Rota</TableHead>
              {!compact && <TableHead>Canal</TableHead>}
              {!compact && <TableHead>Tipo</TableHead>}
              <TableHead className="text-right">Capital</TableHead>
              <TableHead className="text-right">Ganho líquido</TableHead>
              <TableHead className="text-right">ROI</TableHead>
              {!compact && <TableHead className="text-right">Taxa efetiva</TableHead>}
              <TableHead>Confiança</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.map((o, i) => (
              <TableRow key={o.id} className="cursor-pointer" tabIndex={0} onClick={() => setOpen(o)} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setOpen(o); } }} aria-label={`Abrir detalhes: ${o.title}`}>
                <TableCell className="tnum text-muted">{i + 1}</TableCell>
                <TableCell>
                  <div className="font-medium">{o.title}</div>
                  <div className="text-xs text-muted">{o.channel === "digital" ? "Operação digital" : o.city ? CITY_LABEL[o.city] : "Presencial"} · {o.steps.length} etapa{o.steps.length === 1 ? "" : "s"}</div>
                </TableCell>
                {!compact && <TableCell><Badge variant={o.channel === "digital" ? "accent" : "outline"}>{o.channel === "digital" ? "Digital" : "Presencial"}</Badge></TableCell>}
                {!compact && <TableCell className="text-xs">{KIND_LABEL[o.kind]}</TableCell>}
                <TableCell className="tnum text-right">{formatMoney(o.capital_brl, "BRL")}</TableCell>
                <TableCell className="text-right font-semibold" data-testid="gain-cell"><GainCell o={o} /></TableCell>
                <TableCell className="text-right">{o.confidence === "incomplete" ? <span className="tnum text-muted">≈ {formatPercentPlain(o.roi)}</span> : <Delta value={o.roi} />}</TableCell>
                {!compact && <TableCell className="tnum text-right text-muted">{formatRateFixed(o.effective_rate, rateCurrency(o), { decimals: 4 })}</TableCell>}
                <TableCell><ConfidenceBadge c={o.confidence} /></TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
      <RouteDetail opportunity={open} onClose={() => setOpen(null)} />
    </div>
  );
}

function formatPercentPlain(ratio: string) {
  const n = toNumber(ratio);
  return n === null ? "—" : `${Math.abs(n * 100).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 4 })} %`;
}

/** Com `confidence: incomplete` o ganho aparece em cinza como "≈ … · não confirmado" (nunca verde com "+"). */
function GainCell({ o }: { o: Opportunity }) {
  if (o.confidence === "incomplete") {
    return (
      <span className="tnum text-muted">
        <span aria-hidden>≈ </span>
        {formatMoney(o.net_gain_brl, o.valuation_currency)}
        <span className="block text-xs font-normal">não confirmado</span>
      </span>
    );
  }
  return <Delta value={o.net_gain_brl} text={formatMoney(o.net_gain_brl, o.valuation_currency, { sign: true })} />;
}

/** Nunca vermelho: cotado (ganho), estimado (aviso), custo desconhecido (aviso tracejado). */
export function ConfidenceBadge({ c }: { c: Confidence }) {
  if (c === "quoted") return <Badge variant="gain"><span aria-hidden>✓</span> Cotado</Badge>;
  if (c === "estimated") return <Badge variant="warn"><span aria-hidden>≈</span> Estimado</Badge>;
  return <Badge variant="incomplete"><span aria-hidden>?</span> Custo desconhecido</Badge>;
}
