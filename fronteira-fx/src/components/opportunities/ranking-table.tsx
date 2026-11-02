"use client";
import * as React from "react";
import type { Opportunity } from "@/lib/api/types";
import { CITY_LABEL } from "@/lib/api/types";
import { formatMoney, formatPercent, formatRate } from "@/lib/format";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { RouteDetail } from "./route-detail";
import { cn } from "@/lib/utils";

const KIND_LABEL: Record<Opportunity["kind"], string> = { cycle: "Lucro de ciclo", remittance_saving: "Economia em remessa", purchase_saving: "Economia em compra" };

export function RankingTable({ items, title, emptyText }: { items: Opportunity[]; title?: string; emptyText?: string }) {
  const [open, setOpen] = React.useState<Opportunity | null>(null);
  return (
    <div>
      {title && <h3 className="mb-2 text-sm font-semibold">{title}</h3>}
      <Table>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead>#</TableHead>
            <TableHead>Rota</TableHead>
            <TableHead>Canal</TableHead>
            <TableHead>Tipo</TableHead>
            <TableHead className="text-right">Capital</TableHead>
            <TableHead className="text-right">Ganho líquido</TableHead>
            <TableHead className="text-right">ROI</TableHead>
            <TableHead className="text-right">Taxa efetiva</TableHead>
            <TableHead>Confiança</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.length === 0 && (
            <TableRow><TableCell colSpan={9} className="py-6 text-center text-muted">{emptyText ?? "Nenhuma oportunidade."}</TableCell></TableRow>
          )}
          {items.map((o, i) => {
            const gain = Number(o.net_gain_brl);
            return (
              <TableRow key={o.id} className="cursor-pointer" tabIndex={0} onClick={() => setOpen(o)} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setOpen(o); } }} aria-label={`Abrir detalhes: ${o.title}`}>
                <TableCell className="tnum text-muted">{i + 1}</TableCell>
                <TableCell>
                  <div className="font-medium">{o.title}</div>
                  <div className="text-xs text-muted">{o.channel === "digital" ? "Operação digital" : o.city ? CITY_LABEL[o.city] : "Presencial"} · {o.steps.length} etapa{o.steps.length === 1 ? "" : "s"}</div>
                </TableCell>
                <TableCell><Badge variant={o.channel === "digital" ? "accent" : "outline"}>{o.channel === "digital" ? "Digital" : "Presencial"}</Badge></TableCell>
                <TableCell className="text-xs">{KIND_LABEL[o.kind]}</TableCell>
                <TableCell className="tnum text-right">{formatMoney(o.capital_brl, "BRL")}</TableCell>
                <TableCell className={cn("tnum text-right font-semibold", gain > 0 ? "text-gain" : gain < 0 ? "text-loss" : "")}>{formatMoney(o.net_gain_brl, o.valuation_currency, { sign: true })}</TableCell>
                <TableCell className={cn("tnum text-right", gain > 0 ? "text-gain" : gain < 0 ? "text-loss" : "")}>{formatPercent(o.roi, { sign: true })}</TableCell>
                <TableCell className="tnum text-right text-muted">{formatRate(o.effective_rate, o.kind === "cycle" ? "USD" : "PYG")}</TableCell>
                <TableCell><ConfidenceBadge c={o.confidence} /></TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
      <RouteDetail opportunity={open} onClose={() => setOpen(null)} />
    </div>
  );
}

export function ConfidenceBadge({ c }: { c: Opportunity["confidence"] }) {
  if (c === "quoted") return <Badge variant="gain">Cotado</Badge>;
  if (c === "estimated") return <Badge variant="warn">Estimado</Badge>;
  return <Badge variant="loss">Estimativa incompleta</Badge>;
}
