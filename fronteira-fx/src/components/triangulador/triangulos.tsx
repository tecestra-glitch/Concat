"use client";
/**
 * Triângulos ao vivo: ciclos de três pernas no grafo de posições, com lucro líquido, ROI e confiança. Cada triângulo
 * sai com o rótulo Executável (só com cotação firme) ou Referência. É leitura e simulação: não há ação de envio.
 */
import * as React from "react";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { FxCard } from "@/components/ui/fx/fx-card";
import { FxChip } from "@/components/ui/fx/fx-chip";
import { FxSkeleton } from "@/components/ui/fx/fx-skeleton";
import { CurrencyFlag, type FlagCode } from "@/components/ui/currency-flag";
import Link from "next/link";
import { useAccounts, useTriangles } from "@/lib/queries";
import type { Cycle } from "@/lib/api/types";
import {
  NO_BALANCE_NOTE,
  SIMULATION_NOTE,
  confidenceLabel,
  currencyOfNode,
  formatCoinAmount,
  formatPctRatio,
  gainTone,
  hasNoBalance,
  triangleIsExecutable,
  venueOfNode,
} from "@/lib/api/triangulador";
import { CardGrid, SourceLine, Notice, Tag } from "./shared";

const ROUTES = [
  { id: "celular", label: "Pelo celular" },
  { id: "todos", label: "Inclui presencial (opcional)" },
] as const;

const GAIN_CLASS = { gain: "text-gain-strong", loss: "text-loss", flat: "" } as const;

const FLAGS = new Set<FlagCode>(["BRL", "USD", "PYG", "ARS", "EUR", "USDT"]);

function Node({ node }: { node: string }) {
  const code = currencyOfNode(node);
  const venue = venueOfNode(node);
  return (
    <span className="inline-flex min-w-0 items-center gap-1.5 rounded-chip border border-border bg-background/60 px-2 py-1 text-xs">
      {/* CurrencyFlag já escreve o código ao lado da bandeira: o texto não se repete */}
      {FLAGS.has(code as FlagCode) ? <CurrencyFlag code={code as FlagCode} className="tabular-nums" /> : <span className="font-medium tabular-nums">{code}</span>}
      {venue && <span className="truncate text-muted">@{venue}</span>}
    </span>
  );
}

export function TriangleCard({ c, index }: { c: Cycle; index: number }) {
  const executable = triangleIsExecutable(c);
  const startCode = currencyOfNode(c.start);
  const titleId = `tri-${index}`;
  const net = c.gain_by_currency;
  const tone = gainTone(c.gain);
  return (
    <li className="min-w-0">
      <FxCard className="min-w-0 p-4" data-testid="triangle-card" data-executable={executable ? "true" : "false"}>
        <article aria-labelledby={titleId} className="grid min-w-0 gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <h2 id={titleId} className="text-heading font-semibold">Triângulo {index + 1}</h2>
            <Tag executable={executable} />
            <FxChip tone={c.confidence === "quoted" ? "gain" : "warn"}>{confidenceLabel(c.confidence)}</FxChip>
            {c.requires_declaration && <FxChip tone="warn">declaração acima de US$ 10 mil</FxChip>}
          </div>
          <div className="flex min-w-0 flex-wrap items-center gap-1.5" aria-label={`Caminho ${c.path.join(" para ")}`}>
            {c.path.map((n, i) => (
              <React.Fragment key={`${n}-${i}`}>
                {i > 0 && <span aria-hidden className="text-muted">→</span>}
                <Node node={n} />
              </React.Fragment>
            ))}
          </div>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm tabular-nums sm:grid-cols-4">
            <div className="min-w-0">
              <dt className="text-xs text-muted">Entra</dt>
              <dd className="break-words">{formatCoinAmount(c.amount_in, startCode)}</dd>
            </div>
            <div className="min-w-0">
              <dt className="text-xs text-muted">Sai</dt>
              <dd className="break-words">{formatCoinAmount(c.amount_out, startCode)}</dd>
            </div>
            <div className="min-w-0">
              <dt className="text-xs text-muted">Ganho líquido ({startCode})</dt>
              <dd className={`break-words font-medium ${GAIN_CLASS[tone]}`} data-tone={tone}>
                {formatCoinAmount(c.gain, startCode)}
              </dd>
            </div>
            <div className="min-w-0">
              <dt className="text-xs text-muted">ROI</dt>
              <dd className={`break-words ${GAIN_CLASS[gainTone(c.roi)]}`}>{formatPctRatio(c.roi)}</dd>
            </div>
          </dl>
          {net && (
            <p className="text-xs text-muted tabular-nums">
              Em outras moedas:{" "}
              {Object.entries(net)
                .map(([code, v]) => `${code} ${v === null ? "não converte" : formatCoinAmount(v, code)}`)
                .join(" · ")}
            </p>
          )}
          <p className="text-xs text-muted">{c.minutes} min estimados · {SIMULATION_NOTE}</p>
        </article>
      </FxCard>
    </li>
  );
}

export function Triangulos() {
  const [route, setRoute] = React.useState<"celular" | "todos">("celular");
  const q = useTriangles({ limit: 50, route });
  const accounts = useAccounts();
  const list = q.data ?? [];
  const simulatedBalance = accounts.data !== undefined && hasNoBalance(accounts.data);
  return (
    <div className="grid min-w-0 gap-4">
      <p className="text-body text-muted">
        Triângulos de três pernas no seu grafo de posições, ordenados pelo ganho. Cada um tem rótulo de executável ou de referência.
        Ninguém envia ordem daqui: a tela só lê e simula.
      </p>
      <div role="group" aria-label="Quais pernas entram" className="flex flex-wrap gap-2">
        {ROUTES.map((r) => (
          <button
            key={r.id}
            type="button"
            aria-pressed={route === r.id}
            onClick={() => setRoute(r.id)}
            className="inline-flex min-h-11 items-center rounded-control border border-border px-3 text-sm aria-pressed:border-accent aria-pressed:bg-surface-2 aria-pressed:font-medium sm:min-h-9"
          >
            {r.label}
          </button>
        ))}
      </div>
      <Notice>{SIMULATION_NOTE}</Notice>
      {simulatedBalance && (
        <div className="grid gap-1 rounded-control border border-warn/40 bg-surface-2 px-3 py-2 text-xs" data-testid="no-balance-note">
          <p>{NO_BALANCE_NOTE}</p>
          <Link href="/contas" className="inline-flex min-h-11 w-fit items-center font-medium underline underline-offset-2 sm:min-h-8">
            Abrir Contas e cartões
          </Link>
        </div>
      )}
      {!q.isError && (
        <SourceLine source="grafo de posições (motor de triângulos, atualizado a cada 60 s)" at={q.dataUpdatedAt ? new Date(q.dataUpdatedAt).toISOString() : null} />
      )}
      {q.isLoading ? (
        <div role="status" aria-label="Carregando triângulos" className="grid gap-3">
          <span className="sr-only">Carregando…</span>
          <FxSkeleton className="h-40" />
          <FxSkeleton className="h-40" />
        </div>
      ) : q.isError ? (
        <ErrorState title="Os triângulos não carregaram" error={q.error} onRetry={() => void q.refetch()} />
      ) : list.length === 0 ? (
        <EmptyState kind="no-data" title="Nenhum triângulo agora" description="Nenhuma volta de três pernas fecha com as cotações vivas agora. O motor recalcula a cada 60 s." />
      ) : (
        <CardGrid label="Triângulos encontrados">
          {list.map((c, i) => (
            <TriangleCard key={`${c.start}-${c.path.join(">")}-${i}`} c={c} index={i} />
          ))}
        </CardGrid>
      )}
    </div>
  );
}
