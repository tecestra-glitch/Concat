"use client";
import Link from "next/link";
import { PageHeader } from "@/components/shell/page-header";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { TableSkeleton } from "@/components/ui/table-skeleton";
import { ErrorState } from "@/components/ui/error-state";
import { EmptyState } from "@/components/ui/empty-state";
import { formatDateTime, formatMoney } from "@/lib/format";
import { usePlans } from "@/lib/queries";
import { PLAN_STATUS_LABEL } from "@/lib/plans";
import { cn } from "@/lib/utils";
import { PLAN_TONE, gainPresentation } from "./plan-helpers";
import type { Plan } from "@/lib/api/types";
import { cycleCurrency, formatMinutes, pathLabel } from "../opportunities/cycle-helpers";

export function PlansList() {
  const q = usePlans();
  return (
    <div className="space-y-4">
      <PageHeader title="Planos" description="Planos de execução gerados a partir de um ciclo do cruzamento. Nada aqui move dinheiro: você segue os passos por conta própria e registra o resultado.">
        <Link href="/oportunidades" className="text-sm text-accent underline">Gerar um plano em Oportunidades</Link>
      </PageHeader>
      <Card>
        <CardContent className="p-0 sm:p-2">
          {q.isLoading ? (
            <TableSkeleton rows={3} cols={6} />
          ) : q.isError ? (
            <ErrorState title="Os planos não carregaram" error={q.error} onRetry={() => void q.refetch()} />
          ) : !q.data || q.data.length === 0 ? (
            <EmptyState kind="no-data" compact title="Nenhum plano ainda" description="Abra um ciclo lucrativo em Oportunidades e toque em «Gerar plano». Ele aparece aqui." />
          ) : (
            <>
              {/* Celular: cada plano é um cartão inteiro clicável, sem rolagem lateral para achar o "Abrir". */}
              <ul className="space-y-2 p-2 sm:hidden" aria-label="Lista de planos">
                {q.data.map((p) => (
                  <li key={p.id}>
                    <PlanCard plan={p} />
                  </li>
                ))}
              </ul>
              <div className="hidden sm:block">
                <Table scrollLabel="Lista de planos (rola para o lado)">
                  <TableHeader>
                    <TableRow className="hover:bg-transparent">
                      <TableHead>Status</TableHead>
                      <TableHead>Caminho</TableHead>
                      <TableHead className="text-right">Capital</TableHead>
                      <TableHead className="text-right">Ganho esperado</TableHead>
                      <TableHead className="text-right">Prazo</TableHead>
                      <TableHead>Criado em</TableHead>
                      <TableHead><span className="sr-only">Abrir</span></TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {q.data.map((p) => (
                      <TableRow key={p.id} data-testid="plan-row" data-status={p.status}>
                        <TableCell><Badge variant={PLAN_TONE[p.status]}>{PLAN_STATUS_LABEL[p.status]}</Badge></TableCell>
                        <TableCell className="max-w-[18rem] break-words text-xs">{pathLabel(p.path)}</TableCell>
                        <TableCell className="tnum text-right">{formatMoney(p.amount_in, cycleCurrency(p.start))}</TableCell>
                        <GainCell plan={p} />
                        <TableCell className="tnum text-right text-muted">{formatMinutes(p.minutes)}</TableCell>
                        <TableCell className="text-xs text-muted">{formatDateTime(p.created_at)}</TableCell>
                        <TableCell><Link href={`/planos/${p.id}`} className="text-accent underline" aria-label={`Abrir plano de ${formatDateTime(p.created_at)}`}>Abrir</Link></TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

/** Um plano no celular: o cartão inteiro é o link para abrir o plano. */
function PlanCard({ plan: p }: { plan: Plan }) {
  const g = gainPresentation(p.gain_expected, p.currency, p.confidence);
  return (
    <Link
      href={`/planos/${p.id}`}
      data-testid="plan-card"
      data-status={p.status}
      aria-label={`Abrir plano de ${formatDateTime(p.created_at)}`}
      className="block rounded-md border border-border p-3 hover:bg-surface-2"
    >
      <span className="flex items-center justify-between gap-2">
        <Badge variant={PLAN_TONE[p.status]}>{PLAN_STATUS_LABEL[p.status]}</Badge>
        <span className="text-sm font-medium text-accent underline">Abrir</span>
      </span>
      <span className="mt-2 block break-words text-xs">{pathLabel(p.path)}</span>
      <span className="mt-1 flex flex-wrap justify-between gap-x-3 text-sm">
        <span className="tnum">Capital {formatMoney(p.amount_in, cycleCurrency(p.start))}</span>
        <span className={cn("tnum", g.tone === "gain" && "text-gain", g.tone === "loss" && "text-loss", g.tone === "muted" && "text-muted")}>
          Ganho {g.text}
          {p.confidence === "incomplete" && <span className="block text-xs text-muted">não confirmado</span>}
        </span>
      </span>
      <span className="mt-1 block text-xs text-muted">Criado em {formatDateTime(p.created_at)}</span>
    </Link>
  );
}

/** Ganho esperado: ≈ e tom neutro quando o custo não está confirmado; "+" e verde só com ganho confirmado. */
function GainCell({ plan }: { plan: Plan }) {
  const g = gainPresentation(plan.gain_expected, plan.currency, plan.confidence);
  return (
    <TableCell className={cn("tnum text-right", g.tone === "gain" && "text-gain", g.tone === "loss" && "text-loss", g.tone === "muted" && "text-muted")}>
      {g.text}
      {plan.confidence === "incomplete" && <span className="block text-xs text-muted">não confirmado</span>}
    </TableCell>
  );
}
