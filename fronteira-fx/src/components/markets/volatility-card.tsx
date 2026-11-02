"use client";
import * as React from "react";
import type { HistoryPoint } from "@/lib/api/types";
import { computeVolatility } from "@/lib/volatility";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

export function VolatilityCard({ points, now }: { points: HistoryPoint[]; now?: number }) {
  const obs = React.useMemo(() => points.filter((p) => p.mid !== null).map((p) => ({ t: Date.parse(p.t), value: Number(p.mid) })), [points]);
  const ref = now ?? (obs.length ? Math.max(...obs.map((o) => o.t)) : 0);
  const v1h = computeVolatility(obs, 60 * 60 * 1000, ref);
  const v24h = computeVolatility(obs, 24 * 60 * 60 * 1000, ref);
  const first = obs[0]?.value;
  const last = obs[obs.length - 1]?.value;
  const change = first && last ? ((last - first) / first) * 100 : null;
  return (
    <Card data-testid="volatility-card">
      <CardHeader>
        <CardTitle>Variação e volatilidade</CardTitle>
        <CardDescription>Desvio-padrão amostral dos retornos logarítmicos, grade de 5 min. Unidade: % por intervalo de 5 min.</CardDescription>
      </CardHeader>
      <CardContent className="grid grid-cols-3 gap-3 text-sm">
        <div>
          <p className="text-[11px] uppercase tracking-wide text-muted">Variação no período</p>
          <p className={`tnum text-lg font-semibold ${change === null ? "" : change >= 0 ? "text-gain" : "text-loss"}`}>{change === null ? "—" : `${change >= 0 ? "+" : "−"}${Math.abs(change).toFixed(3).replace(".", ",")} %`}</p>
        </div>
        <VolStat label="1 h" v={v1h} />
        <VolStat label="24 h" v={v24h} />
      </CardContent>
    </Card>
  );
}

function VolStat({ label, v }: { label: string; v: ReturnType<typeof computeVolatility> }) {
  return (
    <div>
      <p className="text-[11px] uppercase tracking-wide text-muted">Vol. {label}</p>
      {v.status === "ok" ? (
        <p className="tnum text-lg font-semibold">{v.stdevPctPer5m!.toFixed(4).replace(".", ",")} %</p>
      ) : (
        <Badge variant="warn" className="mt-1">{v.status === "insufficient_data" ? `dados insuficientes (${v.returnsUsed}/${v.minReturns})` : "entrada obsoleta"}</Badge>
      )}
      <p className="text-xs text-muted">cobertura {v.coveragePct.toFixed(0)} % · {v.gaps} lacuna{v.gaps === 1 ? "" : "s"}</p>
    </div>
  );
}
