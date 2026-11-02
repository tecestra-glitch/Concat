"use client";
import * as React from "react";
import type { HistoryPoint } from "@/lib/api/types";
import { computeVolatility } from "@/lib/volatility";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Delta } from "@/components/ui/delta";
import { formatPercent } from "@/lib/format";
import { useNow } from "@/lib/use-now";

/** Janela medida contra o relógio (`useNow`), não contra o último ponto: dado parado vira `stale_input`. */
export function VolatilityCard({ points, now: nowProp }: { points: HistoryPoint[]; now?: number }) {
  const clock = useNow();
  const now = nowProp ?? clock;
  const obs = React.useMemo(() => points.filter((p) => p.mid !== null).map((p) => ({ t: Date.parse(p.t), value: Number(p.mid) })), [points]);
  const ready = now !== 0;
  const v1h = ready ? computeVolatility(obs, 60 * 60 * 1000, now) : null;
  const v24h = ready ? computeVolatility(obs, 24 * 60 * 60 * 1000, now) : null;
  const first = obs[0]?.value;
  const last = obs[obs.length - 1]?.value;
  const change = first && last ? (last - first) / first : null;
  return (
    <Card data-testid="volatility-card">
      <CardHeader>
        <CardTitle>Variação e volatilidade</CardTitle>
        <CardDescription>Desvio-padrão amostral dos retornos logarítmicos, grade de 5 min. Unidade: % por intervalo de 5 min.</CardDescription>
      </CardHeader>
      <CardContent className="grid grid-cols-3 gap-3 text-sm">
        <div>
          <p className="text-xs text-muted">Variação no período</p>
          <p className="text-lg font-semibold"><Delta value={change} /></p>
        </div>
        <VolStat label="1 h" v={v1h} />
        <VolStat label="24 h" v={v24h} />
      </CardContent>
    </Card>
  );
}

function VolStat({ label, v }: { label: string; v: ReturnType<typeof computeVolatility> | null }) {
  return (
    <div>
      <p className="text-xs text-muted">Vol. {label}</p>
      {v === null ? (
        <p className="tnum text-lg font-semibold text-muted">…</p>
      ) : v.status === "ok" ? (
        <p className="tnum text-lg font-semibold">{formatPercent(v.stdevPctPer5m! / 100)}</p>
      ) : (
        <Badge variant="warn" className="mt-1">{v.status === "insufficient_data" ? `dados insuficientes (${v.returnsUsed}/${v.minReturns})` : "entrada obsoleta"}</Badge>
      )}
      {v && <p className="text-xs text-muted">cobertura {formatPercent(v.coveragePct / 100)} · {v.gaps} lacuna{v.gaps === 1 ? "" : "s"}</p>}
    </div>
  );
}
