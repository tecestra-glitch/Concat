"use client";
/**
 * Monitor ao vivo: estado do agendador adaptativo por fonte (módulo watch) e linha do tempo das
 * mudanças reais detectadas. Em modo demonstração o store de demo avança as sondagens agendadas.
 */
import * as React from "react";
import { PageHeader } from "@/components/shell/page-header";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { useSources } from "@/lib/queries";
import { useSettings } from "@/lib/settings";
import { useChanges, useWatchStatuses } from "./use-watch";
import { StatRow } from "./stat-row";
import { WatchTable } from "./watch-table";
import { ChangeTimeline } from "./change-timeline";

export function Monitor() {
  const { mode } = useSettings();
  const statuses = useWatchStatuses();
  const changes = useChanges({});
  const { data: sources = [] } = useSources();
  const names = React.useMemo(() => Object.fromEntries(sources.map((s) => [s.id, s.name])), [sources]);
  const rows = statuses.data ?? [];
  return (
    <div className="space-y-4">
      <PageHeader title="Monitor ao vivo" description="Sites sem API são sondados de forma adaptativa (requisição condicional, hash do conteúdo, intervalo que encurta quando a fonte muda e recua após erros, nunca abaixo de 60 s) e cada mudança real é emitida no stream no mesmo instante." />
      {mode === "demo" && <p className="text-xs text-warn">Demonstração: as sondagens são simuladas localmente; nenhum site é acessado.</p>}
      <StatRow statuses={rows} changes={changes.data ?? []} />
      <Card data-testid="watch-status">
        <CardHeader className="flex-row items-start justify-between gap-2">
          <div>
            <CardTitle>Sondagem por fonte</CardTitle>
            <CardDescription>Intervalo atual dentro dos limites mínimo e máximo, contagem para a próxima leitura, última mudança e erros seguidos. «Sondar agora» força uma leitura imediata respeitando o limite da fonte.</CardDescription>
          </div>
          <Badge variant="outline">{rows.length} fonte{rows.length === 1 ? "" : "s"}</Badge>
        </CardHeader>
        <CardContent className="p-2 sm:p-2">
          {statuses.isLoading ? (
            <Skeleton className="h-40" />
          ) : statuses.isError ? (
            <p role="alert" className="p-4 text-sm text-loss">Falha ao carregar o monitor: {(statuses.error as Error).message}</p>
          ) : (
            <WatchTable statuses={rows} names={names} />
          )}
        </CardContent>
      </Card>
      <ChangeTimeline sources={sources} names={names} />
    </div>
  );
}
