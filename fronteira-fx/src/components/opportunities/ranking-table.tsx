"use client";
import * as React from "react";
import type { Confidence, Opportunity } from "@/lib/api/types";
import { CITY_LABEL } from "@/lib/api/types";
import { formatMoney, toNumber } from "@/lib/format";
import { formatRateFixed } from "@/components/ui/rate";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { CurrencyFlag } from "@/components/ui/currency-flag";
import { Delta } from "@/components/ui/delta";
import { EmptyState } from "@/components/ui/empty-state";
import { RouteDetail } from "./route-detail";

const KIND_LABEL: Record<Opportunity["kind"], string> = { cycle: "Lucro de ciclo", remittance_saving: "Economia em remessa", purchase_saving: "Economia em compra" };

/** Moeda da taxa efetiva: a do destino da última etapa (sem heurística por tipo). */
function rateCurrency(o: Opportunity) {
  return o.steps.at(-1)?.to.currency ?? o.valuation_currency;
}

/** Moedas da rota, sem repetição consecutiva, na ordem em que o dinheiro passa (BRL → PYG → USD → BRL). */
export function routeCurrencies(o: Opportunity): Opportunity["valuation_currency"][] {
  const out: Opportunity["valuation_currency"][] = [];
  for (const s of o.steps) {
    for (const c of [s.from.currency, s.to.currency]) {
      if (out.at(-1) !== c) out.push(c);
    }
  }
  return out.length ? out : [o.valuation_currency];
}

/**
 * Ranking. Ganho líquido, ROI e taxa efetiva são `.fx-num` (sem quebra de linha). Capital, tipo e etapas ficam no
 * subtítulo da rota (OP2), e a rota mostra as bandeiras das moedas (OP3). `compact` (ex.: a home) tira a coluna de
 * confiança, que passa para a própria rota; a taxa efetiva só aparece a partir de xl. O detalhe da rota tem tudo.
 */
export function RankingTable({ items, title, emptyText, compact = false }: { items: Opportunity[]; title?: string; emptyText?: string; compact?: boolean }) {
  const [open, setOpen] = React.useState<Opportunity | null>(null);
  return (
    <div>
      {title && <h3 className="mb-2 text-body font-semibold">{title}</h3>}
      {items.length === 0 ? (
        <EmptyState kind="no-data" compact title={emptyText ?? "Nenhuma oportunidade"} description="O ranking vem do motor do backend; quando uma rota passar nos critérios, ela aparece aqui." />
      ) : (
        <Table scrollLabel="Ranking de oportunidades (rola para o lado)">
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead>#</TableHead>
              <TableHead>Rota</TableHead>
              {!compact && <TableHead>Canal</TableHead>}
              <TableHead className="text-right">Ganho líquido</TableHead>
              <TableHead className="text-right">ROI</TableHead>
              {!compact && <TableHead className="hidden text-right xl:table-cell">Taxa efetiva</TableHead>}
              {!compact && <TableHead>Confiança</TableHead>}
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.map((o, i) => (
              <TableRow key={o.id} className="cursor-pointer hover:bg-surface-3" tabIndex={0} onClick={() => setOpen(o)} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setOpen(o); } }} aria-label={`Abrir detalhes: ${o.title}`}>
                <TableCell className="fx-tnum text-muted">{i + 1}</TableCell>
                <TableCell className="min-w-0">
                  <div className="font-medium">{o.title}</div>
                  <div className="text-caption text-muted">
                    <span className="fx-tnum">{formatMoney(o.capital_brl, "BRL")}</span> · {KIND_LABEL[o.kind]} · {o.steps.length} etapa{o.steps.length === 1 ? "" : "s"}
                    {o.channel !== "digital" && <> · {o.city ? CITY_LABEL[o.city] : "Presencial"}</>}
                  </div>
                  <div className="mt-1 flex flex-wrap items-center gap-x-1.5 gap-y-1 text-caption">
                    {routeCurrencies(o).map((c, k) => (
                      <React.Fragment key={`${c}-${k}`}>
                        {k > 0 && <span aria-hidden className="text-muted">→</span>}
                        <CurrencyFlag code={c} />
                      </React.Fragment>
                    ))}
                  </div>
                  {compact && <div className="mt-1"><ConfidenceBadge c={o.confidence} /></div>}
                </TableCell>
                {!compact && <TableCell><Badge variant={o.channel === "digital" ? "accent" : "outline"}>{o.channel === "digital" ? "Digital" : "Presencial"}</Badge></TableCell>}
                <TableCell className="fx-num font-semibold" data-testid="gain-cell"><GainCell o={o} /></TableCell>
                <TableCell className="fx-num">{o.confidence === "incomplete" ? <span className="text-muted">≈ {formatPercentPlain(o.roi)}</span> : <Delta value={o.roi} />}</TableCell>
                {!compact && <TableCell className="fx-num hidden text-muted xl:table-cell">{formatRateFixed(o.effective_rate, rateCurrency(o), { decimals: 4 })}</TableCell>}
                {!compact && <TableCell><ConfidenceBadge c={o.confidence} /></TableCell>}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
      <RouteDetail opportunity={open} onClose={() => setOpen(null)} />
    </div>
  );
}

export function formatPercentPlain(ratio: string) {
  const n = toNumber(ratio);
  return n === null ? "—" : `${Math.abs(n * 100).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 4 })} %`;
}

/** Com `confidence: incomplete` o ganho aparece em cinza como "≈ … · não confirmado" (nunca verde com "+"). */
export function GainCell({ o }: { o: Opportunity }) {
  if (o.confidence === "incomplete") {
    return (
      <span className="tnum text-muted">
        <span aria-hidden>≈ </span>
        {formatMoney(o.net_gain_brl, o.valuation_currency)}
        <span className="block text-caption font-normal">não confirmado</span>
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
