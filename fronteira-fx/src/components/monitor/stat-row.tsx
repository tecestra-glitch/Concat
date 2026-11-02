"use client";
import { Card } from "@/components/ui/card";
import { countRecent, formatInterval, summarizeWatch, type Change, type WatchStatus } from "@/lib/api/watch";
import { useTicker } from "./use-ticker";

export function StatRow({ statuses, changes }: { statuses: WatchStatus[]; changes: Change[] }) {
  const now = useTicker();
  const sum = summarizeWatch(statuses);
  const lastHour = now === 0 ? null : countRecent(changes, now, 3600);
  return (
    <dl className="grid gap-3 sm:grid-cols-3" data-testid="watch-stats">
      <Card className="p-3">
        <dt className="text-[11px] uppercase tracking-wide text-muted">Fontes monitoradas</dt>
        <dd className="mt-1 flex flex-wrap items-baseline gap-x-3 gap-y-1 text-sm">
          <span className="tnum text-xl font-semibold">{statuses.length}</span>
          <span className="tnum text-gain">{sum.ok} ok</span>
          <span className="tnum text-warn">{sum.degraded} degradada{sum.degraded === 1 ? "" : "s"}</span>
          <span className="tnum text-loss">{sum.blocked} bloqueada{sum.blocked === 1 ? "" : "s"}</span>
        </dd>
      </Card>
      <Card className="p-3">
        <dt className="text-[11px] uppercase tracking-wide text-muted">Mudanças na última hora</dt>
        <dd className="mt-1 text-sm">
          <span className="tnum text-xl font-semibold">{lastHour === null ? "…" : lastHour}</span>
          <span className="ml-2 text-muted">de {changes.length} nas últimas 24 h</span>
        </dd>
      </Card>
      <Card className="p-3">
        <dt className="text-[11px] uppercase tracking-wide text-muted">Intervalo mediano</dt>
        <dd className="mt-1 text-sm">
          <span className="tnum text-xl font-semibold">{sum.medianIntervalS === null ? "—" : formatInterval(sum.medianIntervalS)}</span>
          <span className="ml-2 text-muted">{sum.enabled} fonte{sum.enabled === 1 ? "" : "s"} ativa{sum.enabled === 1 ? "" : "s"} · mín. 60 s</span>
        </dd>
      </Card>
    </dl>
  );
}
