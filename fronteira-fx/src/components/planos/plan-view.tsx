"use client";
/**
 * Tela de um plano de execução: passos em checklist, aprovar ou recusar, marcar passo feito com o valor real,
 * esperado × realizado e a contagem até a cotação expirar. Nada aqui executa operação financeira: os botões
 * só gravam a decisão e o resultado que o dono informa.
 */
import * as React from "react";
import Link from "next/link";
import { Check, TriangleAlert } from "lucide-react";
import { PageHeader } from "@/components/shell/page-header";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { TableSkeleton } from "@/components/ui/table-skeleton";
import { ErrorState } from "@/components/ui/error-state";
import { formatCountdown, secondsUntil } from "@/lib/api/watch";
import { formatDateTime, formatMoney, parseDecimalPtBR } from "@/lib/format";
import { useMounted, useNow } from "@/lib/use-now";
import { usePlan, usePlanDecision } from "@/lib/queries";
import { applyPlanClock, canApprove, canCompleteStep, canReject, nextPendingStep, progressOf, quoteDeadlineMs, resultOf, PLAN_STATUS_LABEL } from "@/lib/plans";
import type { Plan, PlanStep } from "@/lib/api/types";
import { cn } from "@/lib/utils";
import { CYCLE_CURRENCIES, formatMinutes, pathLabel } from "../opportunities/cycle-helpers";
import { ConfidenceBadge } from "../opportunities/ranking-table";
import { LegChannel } from "../opportunities/leg-channel";
import { NO_MONEY_MOVED, PLAN_TONE, STEP_STATUS_LABEL, stepCounter } from "./plan-helpers";

const currencyOfNode = (node: string) => node.split("@")[0] as Plan["currency"];

export function PlanView({ id }: { id: string }) {
  const q = usePlan(id);
  const now = useNow();
  const mounted = useMounted();
  const decide = usePlanDecision(id);

  if (q.isLoading) return <TableSkeleton rows={4} cols={4} />;
  if (q.isError) return <ErrorState title="O plano não carregou" error={q.error} onRetry={() => void q.refetch()} />;
  const plan = q.data;
  if (!plan) return null;

  const view = applyPlanClock(plan, now);
  const next = nextPendingStep(view);
  const live = view.status === "proposed" || view.status === "approved";
  const progress = progressOf(view);
  const result = resultOf(view);
  const expiresIso = live ? new Date(quoteDeadlineMs(plan)).toISOString() : null;
  const expiresIn = expiresIso && mounted ? formatCountdown(expiresIso, now) : "—";
  const secondsLeft = expiresIso && mounted ? secondsUntil(expiresIso, now) : null;
  const busy = decide.approve.isPending || decide.reject.isPending || decide.completeStep.isPending;
  const errorText = [decide.approve.error, decide.reject.error, decide.completeStep.error].find(Boolean);

  return (
    <div className="space-y-4">
      <PageHeader title="Plano de execução" description={`Caminho: ${pathLabel(plan.path)}`}>
        <Badge variant={PLAN_TONE[view.status]} data-testid="plan-status">{PLAN_STATUS_LABEL[view.status]}</Badge>
        <Link href="/planos" className="text-sm text-accent underline">Todos os planos</Link>
      </PageHeader>

      <div role="note" className="flex gap-2 rounded-md border border-border bg-surface-2/60 p-3 text-sm" data-testid="no-money-notice">
        <TriangleAlert className="mt-0.5 size-4 shrink-0 text-warn" aria-hidden />
        <p>{NO_MONEY_MOVED}</p>
      </div>

      {view.status === "expired" && (
        <p role="alert" className="rounded-md border border-loss/60 bg-loss/10 p-3 text-sm text-loss" data-testid="plan-expired">
          Este plano expirou: a cotação mais velha passou do limite de {Math.round(plan.quote_max_age_s / 60)} min. Gere um novo plano a partir do cruzamento.
        </p>
      )}
      {live && (
        <p className="text-sm" data-testid="plan-countdown" aria-live="off">
          Cotação válida por mais <span className="tnum font-semibold">{secondsLeft === 0 ? "pouco" : expiresIn}</span>. Depois disso o plano expira. Ele expira só antes do primeiro passo.
        </p>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Resumo</CardTitle>
          <CardDescription>Calculado em {formatDateTime(plan.quotes_as_of)} · {formatMinutes(plan.minutes)} no total · {plan.data_mode === "demo" ? "dados ilustrativos da demonstração" : `dados ${plan.data_mode}`}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
            <Item k="Capital" v={formatMoney(plan.amount_in, plan.currency)} />
            <Item k="Saída esperada" v={formatMoney(plan.amount_out_expected, plan.currency)} />
            <Item k={`Ganho esperado (${plan.currency})`} v={formatMoney(plan.gain_expected, plan.currency, { sign: true })} tone="gain" strong />
            <div className="min-w-0"><dt className="text-xs text-muted">Confiança</dt><dd className="mt-0.5"><ConfidenceBadge c={plan.confidence} /></dd></div>
          </dl>
          <ul className="grid grid-cols-3 gap-2 text-sm" aria-label="Ganho esperado nas três moedas">
            {CYCLE_CURRENCIES.map((cur) => {
              const v = plan.gain_by_currency?.[cur] ?? null;
              return (
                <li key={cur} className={cn("rounded-md border p-2", cur === plan.currency ? "border-accent/60 bg-accent/10" : "border-border")} data-currency={cur}>
                  <p className="text-xs text-muted">{cur === plan.currency ? `${cur} (partida)` : cur}</p>
                  <p className="tnum font-medium">{v === null ? "não convertido" : formatMoney(v, cur, { sign: true })}</p>
                </li>
              );
            })}
          </ul>
          {plan.requires_declaration && (
            <p role="note" className="rounded-md border border-warn/60 bg-warn/10 p-2 text-xs" data-testid="plan-declaration">
              <span className="font-medium text-warn">Declaração: </span>uma perna de fronteira passa de US$ 10 mil. Confira antes de atravessar.
            </p>
          )}
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => decide.approve.mutate()} disabled={!canApprove(plan, now) || busy} data-testid="approve-plan">Aprovar plano</Button>
            <Button variant="outline" onClick={() => decide.reject.mutate()} disabled={!canReject(plan, now) || busy} data-testid="reject-plan">Recusar plano</Button>
          </div>
          {live && <p className="text-xs text-muted">Aprovar só registra a sua decisão. Nenhum banco, casa ou API é chamado.</p>}
          {errorText && <p role="alert" className="text-xs text-loss">{errorText instanceof Error ? errorText.message : "Não foi possível salvar"}</p>}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Passos</CardTitle>
          <CardDescription>Em ordem, um de cada vez. Ao concluir cada passo, informe o valor que você recebeu de fato.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-sm text-muted" data-testid="plan-progress">Feitos: {stepCounter(progress.done, progress.total)}</p>
          <ol className="space-y-2" aria-label="Passos do plano">
            {[...view.steps].sort((a, b) => a.n - b.n).map((step) => (
              <StepRow
                key={step.n}
                step={step}
                isNext={next?.n === step.n}
                actionable={canCompleteStep(view, step.n, now)}
                busy={busy}
                onDone={(actual_out, note) => decide.completeStep.mutate({ n: step.n, body: { actual_out, note } })}
              />
            ))}
          </ol>
        </CardContent>
      </Card>

      {result && (
        <Card>
          <CardHeader>
            <CardTitle>Esperado × realizado</CardTitle>
            <CardDescription>Plano concluído. A diferença entra no diário como resultado do plano.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <dl className="grid grid-cols-3 gap-3 text-sm" data-testid="plan-result">
              <Item k="Esperado" v={formatMoney(result.expected, plan.currency)} />
              <Item k="Realizado" v={formatMoney(result.realized, plan.currency)} />
              <Item k="Diferença" v={formatMoney(result.difference, plan.currency, { sign: true })} tone={Number(result.difference) < 0 ? "loss" : "gain"} strong />
            </dl>
            <StepsResult plan={view} />
          </CardContent>
        </Card>
      )}
      {!result && view.steps.some((s) => s.status === "done") && <StepsResult plan={view} />}
    </div>
  );
}

function StepRow({ step, isNext, actionable, busy, onDone }: { step: PlanStep; isNext: boolean; actionable: boolean; busy: boolean; onDone: (actual: string, note?: string) => void }) {
  const done = step.status === "done";
  const toC = currencyOfNode(step.to);
  const status = done ? STEP_STATUS_LABEL.done : isNext ? "Próximo" : STEP_STATUS_LABEL.pending;
  return (
    <li className={cn("rounded-md border p-3 text-sm", done ? "border-gain/40 bg-gain/5" : isNext ? "border-accent/60 bg-accent/5" : "border-border")} data-testid="plan-step" data-status={step.status} data-next={isNext}>
      <div className="flex items-start gap-3">
        <span className={cn("tnum mt-0.5 grid size-6 shrink-0 place-items-center rounded-full border text-xs font-semibold", done ? "border-gain bg-gain/15 text-gain-strong" : "border-border text-muted")} aria-hidden>
          {done ? <Check className="size-3.5" /> : step.n}
        </span>
        <div className="min-w-0 flex-1 space-y-1">
          <p className="font-medium">
            <span className="sr-only">Passo {step.n}: </span>
            {step.text}
          </p>
          <p className="flex flex-wrap items-center gap-2 text-xs text-muted">
            <Badge variant={done ? "gain" : isNext ? "accent" : "outline"}>{status}</Badge>
            <span>{formatMinutes(step.minutes)}</span>
            <LegChannel channel={step.channel} />
          </p>
          <p className="tnum text-xs text-muted">Esperado: {formatMoney(step.amount_out_expected, toC)}</p>
          {done && <p className="tnum text-xs">Realizado: {formatMoney(step.actual_out, toC)}{step.note ? ` · ${step.note}` : ""}</p>}
          {isNext && actionable && !done && <StepForm currency={toC} busy={busy} onSubmit={onDone} />}
        </div>
      </div>
    </li>
  );
}

/** Valor realizado do passo: decimal em pt-BR, convertido para string decimal antes de sair da tela (D1). */
function StepForm({ currency, busy, onSubmit }: { currency: Plan["currency"]; busy: boolean; onSubmit: (actual: string, note?: string) => void }) {
  const [value, setValue] = React.useState("");
  const [note, setNote] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const id = React.useId();
  return (
    <form
      className="mt-2 grid gap-2 rounded-md border border-border p-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] sm:items-end"
      onSubmit={(e) => {
        e.preventDefault();
        const canon = parseDecimalPtBR(value);
        if (canon === null) {
          setError(`Informe o valor recebido em ${currency}, ex.: 5.090 ou 1.250,50.`);
          return;
        }
        setError(null);
        onSubmit(canon, note.trim() || undefined);
      }}
    >
      <div className="grid gap-1">
        <Label htmlFor={`${id}-value`}>Valor realizado ({currency})</Label>
        <Input id={`${id}-value`} inputMode="decimal" value={value} onChange={(e) => setValue(e.target.value)} autoComplete="off" aria-invalid={!!error} aria-describedby={error ? `${id}-err` : undefined} />
      </div>
      <div className="grid gap-1">
        <Label htmlFor={`${id}-note`}>Observação (opcional)</Label>
        <Input id={`${id}-note`} value={note} onChange={(e) => setNote(e.target.value)} autoComplete="off" />
      </div>
      <Button type="submit" disabled={busy}>Marcar como feito</Button>
      {error && <p id={`${id}-err`} role="alert" className="text-xs text-loss sm:col-span-3">{error}</p>}
    </form>
  );
}

function StepsResult({ plan }: { plan: Plan }) {
  const steps = [...plan.steps].sort((a, b) => a.n - b.n).filter((s) => s.status === "done");
  if (steps.length === 0) return null;
  return (
    <Table scrollLabel="Esperado e realizado por passo (rola para o lado)">
      <TableHeader>
        <TableRow className="hover:bg-transparent">
          <TableHead>Passo</TableHead>
          <TableHead className="text-right">Esperado</TableHead>
          <TableHead className="text-right">Realizado</TableHead>
          <TableHead className="text-right">Diferença</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {steps.map((s) => {
          const c = currencyOfNode(s.to);
          const diff = Number(s.actual_out) - Number(s.amount_out_expected);
          return (
            <TableRow key={s.n}>
              <TableCell>{s.n}</TableCell>
              <TableCell className="tnum text-right">{formatMoney(s.amount_out_expected, c)}</TableCell>
              <TableCell className="tnum text-right">{formatMoney(s.actual_out, c)}</TableCell>
              <TableCell className={cn("tnum text-right", diff < 0 ? "text-loss" : "text-gain")}>{formatMoney(String(diff), c, { sign: true })}</TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}

function Item({ k, v, tone, strong }: { k: string; v: string; tone?: "gain" | "loss"; strong?: boolean }) {
  return (
    <div className="min-w-0 rounded-md border border-border p-2.5">
      <dt className="text-xs text-muted">{k}</dt>
      <dd className={cn("tnum mt-0.5 break-words font-semibold", strong ? "text-base" : "text-sm", tone === "gain" && "text-gain", tone === "loss" && "text-loss")}>{v}</dd>
    </div>
  );
}
