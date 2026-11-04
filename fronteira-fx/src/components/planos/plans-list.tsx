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
import { PLAN_TONE } from "./plan-helpers";
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
                    <TableCell className="tnum text-right text-gain">{formatMoney(p.gain_expected, p.currency, { sign: true })}</TableCell>
                    <TableCell className="tnum text-right text-muted">{formatMinutes(p.minutes)}</TableCell>
                    <TableCell className="text-xs text-muted">{formatDateTime(p.created_at)}</TableCell>
                    <TableCell><Link href={`/planos/${p.id}`} className="text-accent underline" aria-label={`Abrir plano de ${formatDateTime(p.created_at)}`}>Abrir</Link></TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
