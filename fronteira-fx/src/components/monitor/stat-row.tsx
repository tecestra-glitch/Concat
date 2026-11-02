"use client";
import { Card } from "@/components/ui/card";
import { formatInterval, summarizeWatch, type Change, type WatchStatus } from "@/lib/api/watch";
import { useTicker } from "./use-ticker";
import { changeCounts } from "./stat-helpers";

export function StatRow({ statuses, changes }: { statuses: WatchStatus[]; changes: Change[] }) {
  const now = useTicker();
  const sum = summarizeWatch(statuses);
  const counts = changeCounts(changes, now);
  return (
    <dl className="grid gap-3 sm:grid-cols-3" data-testid="watch-stats">
      <Card className="p-3">
        <dt className="text-xs text-muted">Fontes monitoradas</dt>
        <dd className="mt-1 flex flex-wrap items-baseline gap-x-3 gap-y-1 text-sm">
          <span className="tnum text-xl font-semibold">{statuses.length}</span>
          <span className="tnum text-gain">{sum.ok} ok</span>
          <span className="tnum text-warn">{sum.degraded} degradada{sum.degraded === 1 ? "" : "s"}</span>
          <span className="tnum text-loss">{sum.blocked} bloqueada{sum.blocked === 1 ? "" : "s"}</span>
        </dd>
      </Card>
      <Card className="p-3">
        <dt className="text-xs text-muted">Mudanças na última hora</dt>
        <dd className="mt-1 text-sm">
          <span className="tnum text-xl font-semibold">{counts.lastHour === null ? "…" : counts.lastHour}</span>
          <span className="ml-2 text-muted" data-testid="changes-24h">de {counts.last24h === null ? "…" : counts.last24h} nas últimas 24 h</span>
        </dd>
      </Card>
      <Card className="p-3">
        <dt className="text-xs text-muted">Intervalo mediano</dt>
        <dd className="mt-1 text-sm">
          <span className="tnum text-xl font-semibold">{sum.medianIntervalS === null ? "—" : formatInterval(sum.medianIntervalS)}</span>
          <span className="ml-2 text-muted">{sum.enabled} fonte{sum.enabled === 1 ? "" : "s"} ativa{sum.enabled === 1 ? "" : "s"} · mín. 60 s</span>
        </dd>
      </Card>
    </dl>
  );
}
