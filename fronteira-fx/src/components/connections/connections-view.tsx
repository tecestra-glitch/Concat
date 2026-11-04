"use client";
/**
 * Visual da tela de conexões, sem estado de rede: tudo chega por props, então renderiza igual no teste e no app.
 * Nenhum campo de senha de banco existe aqui; o único campo de segredo é o da chave de API, num diálogo próprio.
 */
import * as React from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { FxChip, type FxChipTone } from "@/components/ui/fx/fx-chip";
import { keyHintText, type Connection, type ConnectionKind, type ConnectionStatus } from "@/lib/api/connections";
import { CATALOG, PATH_LABEL, pathsFor, type CatalogGroup, type CatalogInstitution, type ConnectionPath } from "@/lib/api/connections-catalog";
import type { Mode } from "@/lib/api/types";

export const NO_PASSWORD_BANNER = "O Fronteira FX nunca pede a senha do seu banco.";

const STATUS: Record<ConnectionStatus, { label: string; tone: FxChipTone }> = {
  pending: { label: "Aguardando", tone: "warn" },
  active: { label: "Ativa", tone: "gain" },
  error: { label: "Com erro", tone: "loss" },
};

/** Caminho de conexão a partir do tipo de conexão do servidor (`kind`). */
const PATH_OF_KIND: Record<ConnectionKind, ConnectionPath> = {
  consent: "open_finance",
  readonly_key: "api_key_readonly",
  statement: "statement_import",
  manual: "manual_balance",
};

const METHOD_NOTE: Record<ConnectionPath, string> = {
  open_finance: "Você autoriza no próprio banco, por consentimento.",
  api_key_readonly: "Chave só de leitura: não pode operar nem sacar.",
  statement_import: "Você envia o arquivo; o servidor lê as linhas.",
  manual_balance: "Você informa o saldo em Contas e cartões.",
};

export interface ConnectionsViewProps {
  mode: Mode;
  aggregatorConfigured: boolean;
  connections: Connection[];
  groups?: CatalogGroup[];
  loading?: boolean;
  onOpenFinance: (inst: CatalogInstitution) => void;
  onApiKey: (inst: CatalogInstitution) => void;
  onStatement: (inst: CatalogInstitution) => void;
  onDelete: (conn: Connection) => void;
  busy?: boolean;
}

export function ConnectionsView({ mode, aggregatorConfigured, connections, groups = CATALOG, loading = false, onOpenFinance, onApiKey, onStatement, onDelete, busy = false }: ConnectionsViewProps) {
  return (
    <div className="space-y-6">
      <div role="note" data-testid="no-password-banner" className="rounded-surface border-2 border-accent bg-accent-soft p-4 text-foreground">
        <p className="text-heading font-semibold">{NO_PASSWORD_BANNER}</p>
        <p className="mt-1 text-body text-muted">Conecte só pelos caminhos oficiais de cada instituição: autorização no banco, chave de leitura, extrato ou saldo informado por você.</p>
      </div>

      {mode === "demo" && (
        <p role="note" className="text-caption text-warn" data-testid="connections-demo-note">
          Demonstração — conexões fictícias. Nada é conectado de verdade neste modo.
        </p>
      )}

      <section aria-labelledby="conexoes-ativas" className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <h2 id="conexoes-ativas" className="text-heading font-semibold">Conexões ativas</h2>
          {mode === "demo" && <FxChip tone="demo">demonstração</FxChip>}
        </div>
        {loading && <p className="text-body text-muted">Carregando conexões…</p>}
        {!loading && connections.length === 0 && (
          <EmptyState kind="no-data" title="Nenhuma conexão ainda" description="Escolha uma instituição abaixo. Saldo manual também conta." compact />
        )}
        {connections.length > 0 && (
          <ul className="grid gap-3 md:grid-cols-2" data-testid="connections-list">
            {connections.map((c) => (
              <ConnectionRow key={c.id} conn={c} onDelete={onDelete} busy={busy} />
            ))}
          </ul>
        )}
      </section>

      <div className="space-y-6">
        {groups.map((g) => (
          <section key={g.id} aria-labelledby={`grupo-${g.id}`} className="space-y-3" data-testid="connections-group">
            <div>
              <h2 id={`grupo-${g.id}`} className="text-heading font-semibold">{g.title}</h2>
              <p className="text-caption text-muted">{g.description}</p>
            </div>
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {g.institutions.map((inst) => (
                <InstitutionCard
                  key={inst.id}
                  inst={inst}
                  aggregatorConfigured={aggregatorConfigured}
                  onOpenFinance={onOpenFinance}
                  onApiKey={onApiKey}
                  onStatement={onStatement}
                />
              ))}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}

function ConnectionRow({ conn, onDelete, busy }: { conn: Connection; onDelete: (c: Connection) => void; busy: boolean }) {
  const [confirming, setConfirming] = React.useState(false);
  const st = STATUS[conn.status];
  const hint = keyHintText(conn.key_hint);
  return (
    <li className="rounded-surface border border-border bg-surface p-3 text-body" data-testid="connection-row">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="font-medium">{conn.label}</p>
          <p className="text-caption text-muted">
            {PATH_LABEL[PATH_OF_KIND[conn.kind]]}
            {hint && <> · chave <span className="tnum">{hint}</span></>}
          </p>
        </div>
        <FxChip tone={st.tone}>{st.label}</FxChip>
      </div>
      <div className="mt-2 flex flex-wrap items-center justify-end gap-2">
        {confirming ? (
          <>
            <span className="mr-auto text-caption text-muted">Desconectar {conn.label}?</span>
            <Button variant="ghost" size="sm" onClick={() => setConfirming(false)} disabled={busy}>Cancelar</Button>
            <Button variant="destructive" size="sm" onClick={() => onDelete(conn)} disabled={busy}>Confirmar desconexão</Button>
          </>
        ) : (
          <Button variant="ghost" size="sm" onClick={() => setConfirming(true)} disabled={busy} aria-label={`Desconectar ${conn.label}`}>Desconectar</Button>
        )}
      </div>
    </li>
  );
}

function InstitutionCard({
  inst,
  aggregatorConfigured,
  onOpenFinance,
  onApiKey,
  onStatement,
}: {
  inst: CatalogInstitution;
  aggregatorConfigured: boolean;
  onOpenFinance: (i: CatalogInstitution) => void;
  onApiKey: (i: CatalogInstitution) => void;
  onStatement: (i: CatalogInstitution) => void;
}) {
  return (
    <Card data-testid="institution-card">
      <CardHeader>
        <CardTitle>{inst.name}</CardTitle>
        <CardDescription>Como conectar</CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        {pathsFor(inst).map((path) => {
          const id = `${inst.id}-${path}`;
          if (path === "manual_balance") {
            return (
              <div key={id} className="space-y-0.5">
                <Button asChild variant="secondary" className="w-full justify-start">
                  <Link href="/contas" aria-describedby={`${id}-nota`}>{PATH_LABEL.manual_balance}</Link>
                </Button>
                <p id={`${id}-nota`} className="px-1 text-caption text-muted">{METHOD_NOTE.manual_balance}</p>
              </div>
            );
          }
          if (path === "open_finance") {
            return (
              <div key={id} className="space-y-0.5">
                <Button variant="secondary" className="w-full justify-start" disabled={!aggregatorConfigured} aria-describedby={`${id}-nota`} onClick={() => onOpenFinance(inst)}>
                  {PATH_LABEL.open_finance}
                </Button>
                <p id={`${id}-nota`} className="px-1 text-caption text-muted">
                  {aggregatorConfigured ? METHOD_NOTE.open_finance : <span className="text-warn">Precisa contratar um agregador de Open Finance antes de autorizar.</span>}
                </p>
              </div>
            );
          }
          const onClick = path === "api_key_readonly" ? () => onApiKey(inst) : () => onStatement(inst);
          return (
            <div key={id} className="space-y-0.5">
              <Button variant="secondary" className="w-full justify-start" aria-describedby={`${id}-nota`} onClick={onClick}>
                {PATH_LABEL[path]}
              </Button>
              <p id={`${id}-nota`} className="px-1 text-caption text-muted">{METHOD_NOTE[path]}</p>
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}
