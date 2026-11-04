"use client";
/** Tela de conexões: liga os dados (query e mutações) ao visual puro de `ConnectionsView`. */
import * as React from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ErrorState } from "@/components/ui/error-state";
import { useSettings } from "@/lib/settings";
import { useConnections } from "@/lib/queries";
import { api } from "@/lib/api/client";
import type { Connection } from "@/lib/api/connections";
import type { CatalogInstitution } from "@/lib/api/connections-catalog";
import { ConnectionsView } from "./connections-view";
import { ApiKeyDialog } from "./api-key-dialog";
import { StatementDialog } from "./statement-dialog";
import { useSubmitState } from "@/components/ui/use-submit";

export function ConnectionsScreen() {
  const { mode } = useSettings();
  const q = useConnections();
  const qc = useQueryClient();
  const [apiKeyFor, setApiKeyFor] = React.useState<CatalogInstitution | null>(null);
  const [statementFor, setStatementFor] = React.useState<CatalogInstitution | null>(null);
  const [openFinanceError, setOpenFinanceError] = React.useState<string | null>(null);
  const removal = useSubmitState();
  const openFinance = useMutation({
    mutationFn: (inst: CatalogInstitution) => api.startOpenFinance(mode, inst.id),
    onSuccess: (r) => window.location.assign(r.redirect_url),
    onError: (e: Error) => setOpenFinanceError(e.message),
  });

  const remove = async (conn: Connection) => {
    const ok = await removal.run(async () => {
      await api.deleteConnection(mode, conn.id);
      await qc.invalidateQueries({ queryKey: ["connections", mode] });
    }, "Não foi possível desconectar.");
    return ok;
  };

  const data = q.data;
  return (
    <div className="space-y-4">
      {q.isError && <ErrorState title="As conexões não carregaram" error={q.error} onRetry={() => void q.refetch()} />}
      {openFinanceError && (
        <p role="alert" className="text-caption text-loss">Não foi possível iniciar o Open Finance. {openFinanceError}</p>
      )}
      {removal.error && <p role="alert" className="text-caption text-loss">{removal.error}</p>}
      <ConnectionsView
        mode={mode}
        aggregatorConfigured={data?.aggregator_configured ?? false}
        connections={data?.connections ?? []}
        loading={q.isLoading}
        busy={removal.pending || openFinance.isPending}
        onOpenFinance={(inst) => {
          setOpenFinanceError(null);
          openFinance.mutate(inst);
        }}
        onApiKey={setApiKeyFor}
        onStatement={setStatementFor}
        onDelete={(c) => void remove(c)}
      />
      <ApiKeyDialog open={apiKeyFor !== null} onOpenChange={(o) => !o && setApiKeyFor(null)} inst={apiKeyFor} mode={mode} />
      <StatementDialog open={statementFor !== null} onOpenChange={(o) => !o && setStatementFor(null)} inst={statementFor} mode={mode} />
    </div>
  );
}
