"use client";
import * as React from "react";
import { Radar } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatAge } from "@/lib/format";
import { cn } from "@/lib/utils";
import { WATCH_STATE_LABEL, WATCH_STATE_TONE, formatCountdown, formatInterval, type WatchStatus } from "@/lib/api/watch";
import { useTriggerPoll, useUpdateWatch } from "./use-watch";
import { useTicker } from "./use-ticker";

interface Props {
  statuses: WatchStatus[];
  names: Record<string, string>;
}

/** Wide table from `md` up; stacked cards below (390 px must not scroll horizontally). */
export function WatchTable({ statuses, names }: Props) {
  if (statuses.length === 0) return <p className="p-4 text-center text-sm text-muted">Nenhuma fonte monitorada.</p>;
  return (
    <>
      <div className="hidden md:block">
        <Table scrollLabel="Sondagem por fonte (rola para o lado)">
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead>Fonte</TableHead>
              <TableHead>Ativa</TableHead>
              <TableHead>Intervalo</TableHead>
              <TableHead>Próxima sondagem</TableHead>
              <TableHead>Última mudança</TableHead>
              <TableHead className="text-right">24 h</TableHead>
              <TableHead className="text-right">Erros</TableHead>
              <TableHead>Estado</TableHead>
              <TableHead><span className="sr-only">Ações</span></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {statuses.map((s) => (
              <WatchRow key={s.source_id} s={s} name={names[s.source_id] ?? s.source_id} />
            ))}
          </TableBody>
        </Table>
      </div>
      <ul className="grid gap-2 md:hidden" aria-label="Fontes monitoradas">
        {statuses.map((s) => (
          <WatchCard key={s.source_id} s={s} name={names[s.source_id] ?? s.source_id} />
        ))}
      </ul>
    </>
  );
}

function StatusBadge({ s }: { s: WatchStatus }) {
  return <Badge variant={WATCH_STATE_TONE[s.status] ?? "outline"}>{WATCH_STATE_LABEL[s.status] ?? s.status}</Badge>;
}

function EnableSwitch({ s, name, id }: { s: WatchStatus; name: string; id: string }) {
  const m = useUpdateWatch();
  return <Switch id={id} checked={s.enabled} aria-label={`Monitorar ${name}`} onCheckedChange={(enabled) => m.mutate({ id: s.source_id, patch: { enabled } })} />;
}

/** Ticks every second. Reads 0 before hydration and renders a placeholder so SSR and client agree. */
function Countdown({ s }: { s: WatchStatus }) {
  const now = useTicker();
  if (!s.enabled) return <span className="text-muted">pausada</span>;
  if (now === 0) return <span className="tnum text-muted">…</span>;
  const text = formatCountdown(s.next_run_at, now);
  return (
    <span className={cn("tnum", text === "agora" && "text-accent")} data-testid="next-run">
      {text === "agora" ? "agora" : `em ${text}`}
    </span>
  );
}

function Age({ iso, empty = "sem dados", className }: { iso: string | null; empty?: string; className?: string }) {
  const now = useTicker();
  if (!iso) return <span className={cn("text-muted", className)}>{empty}</span>;
  return <span className={cn("tnum", className)}>{now === 0 ? "…" : formatAge(iso, now)}</span>;
}

function PollButton({ s, name, compact = false }: { s: WatchStatus; name: string; compact?: boolean }) {
  const m = useTriggerPoll();
  const feedback = m.isPending ? null : m.isError ? "falhou" : m.isSuccess ? (m.data ? "mudança detectada" : "sem mudança") : null;
  return (
    <div className={cn("flex items-center gap-2", compact ? "justify-between" : "justify-end")}>
      {feedback && (
        <output className={cn("text-[11px]", m.isError ? "text-loss" : m.data ? "text-gain" : "text-muted")} aria-live="polite">
          {feedback}
        </output>
      )}
      <Button type="button" size="sm" variant="secondary" disabled={m.isPending} aria-label={`Sondar agora: ${name}`} onClick={() => m.mutate(s.source_id)}>
        <Radar className={cn(m.isPending && "animate-pulse")} aria-hidden /> {m.isPending ? "Sondando…" : "Sondar agora"}
      </Button>
    </div>
  );
}

function WatchRow({ s, name }: { s: WatchStatus; name: string }) {
  return (
    <TableRow data-testid="watch-row" data-source={s.source_id} data-last-run={s.last_run_at ?? ""} className={cn(!s.enabled && "bg-surface-2/40 text-muted")}>
      <TableCell>
        <p className="font-medium">{name}</p>
        <p className="tnum text-[11px] text-muted">{s.source_id}</p>
      </TableCell>
      <TableCell><EnableSwitch s={s} name={name} id={`watch-enabled-${s.source_id}`} /></TableCell>
      <TableCell>
        <p className="tnum">{formatInterval(s.interval_s)}</p>
        <p className="tnum text-[11px] text-muted">{formatInterval(s.min_interval_s)} – {formatInterval(s.max_interval_s)}</p>
      </TableCell>
      <TableCell>
        <Countdown s={s} />
        <p className="text-[11px] text-muted">sondada <Age iso={s.last_run_at} empty="nunca" className="text-muted" /></p>
      </TableCell>
      <TableCell><Age iso={s.last_change_at} /></TableCell>
      <TableCell className="tnum text-right">{s.changes_24h}</TableCell>
      <TableCell className={cn("tnum text-right", s.errors_in_row > 0 && "font-semibold text-loss")}>{s.errors_in_row}</TableCell>
      <TableCell><StatusBadge s={s} /></TableCell>
      <TableCell><PollButton s={s} name={name} /></TableCell>
    </TableRow>
  );
}

function WatchCard({ s, name }: { s: WatchStatus; name: string }) {
  return (
    <li data-testid="watch-row" data-source={s.source_id} data-last-run={s.last_run_at ?? ""} className={cn("rounded-md border border-border bg-surface p-3 text-sm", !s.enabled && "bg-surface-2/40 text-muted")}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate font-medium">{name}</p>
          <p className="tnum text-[11px] text-muted">{s.source_id}</p>
        </div>
        <div className="flex items-center gap-2">
          <StatusBadge s={s} />
          <EnableSwitch s={s} name={name} id={`watch-enabled-card-${s.source_id}`} />
        </div>
      </div>
      <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1.5 text-xs">
        <div>
          <dt className="text-muted">Intervalo</dt>
          <dd className="tnum">{formatInterval(s.interval_s)} <span className="text-muted">({formatInterval(s.min_interval_s)} – {formatInterval(s.max_interval_s)})</span></dd>
        </div>
        <div>
          <dt className="text-muted">Próxima sondagem</dt>
          <dd><Countdown s={s} /></dd>
        </div>
        <div>
          <dt className="text-muted">Última sondagem</dt>
          <dd><Age iso={s.last_run_at} empty="nunca" /></dd>
        </div>
        <div>
          <dt className="text-muted">Última mudança</dt>
          <dd><Age iso={s.last_change_at} /></dd>
        </div>
        <div>
          <dt className="text-muted">Mudanças 24 h</dt>
          <dd className="tnum">{s.changes_24h}</dd>
        </div>
        <div>
          <dt className="text-muted">Erros seguidos</dt>
          <dd className={cn("tnum", s.errors_in_row > 0 && "font-semibold text-loss")}>{s.errors_in_row}</dd>
        </div>
      </dl>
      <div className="mt-3"><PollButton s={s} name={name} compact /></div>
    </li>
  );
}
