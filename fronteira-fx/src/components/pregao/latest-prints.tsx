"use client";
import type { ReactElement } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { formatRate } from "@/lib/format";
import { quoteOfPair } from "@/lib/pregao/candles";
import type { Print } from "@/lib/pregao/types";
import { cn } from "@/lib/utils";
import { Delta } from "./delta";
import { ReferenceBadge } from "./reference-badge";

export interface LatestPrintsProps {
  /** Mais recente primeiro. */
  prints: readonly Print[];
  /** Padrão 30. */
  limit?: number;
  loading?: boolean;
  error?: Error | null;
  onRetry?: () => void;
  onSelect?: (key: string) => void;
  className?: string;
}

const TZ = "America/Asuncion";
const TIME = new Intl.DateTimeFormat("pt-BR", { timeZone: TZ, hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" });

/** Hora HH:mm:ss no fuso de exibição da tela. */
export function printTime(iso: string): string {
  return TIME.format(new Date(iso));
}

function rateText(value: string | null, p: Print): string {
  const text = formatRate(value, quoteOfPair(p.pair));
  return p.kind === "market_reference" && value !== null ? `≈ ${text}` : text;
}

function houseCell(p: Print, onSelect?: (key: string) => void): ReactElement {
  const isRef = p.kind === "market_reference";
  const name =
    onSelect && !isRef ? (
      <button
        type="button"
        onClick={() => onSelect(p.key)}
        className="rounded-sm text-left underline-offset-2 hover:underline focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2"
      >
        {p.house}
      </button>
    ) : (
      <span>{p.house}</span>
    );
  return (
    <span className="inline-flex flex-wrap items-center gap-1">
      {name}
      {isRef ? <ReferenceBadge compact /> : null}
      {p.incomplete ? <Badge variant="warn">incompleta</Badge> : null}
    </span>
  );
}

/**
 * Últimas atualizações de cotação publicadas pelas casas. Não são negócios fechados.
 * Sem estado próprio e sem aria-live: a lista muda a cada minuto e não deve ser anunciada.
 */
export function LatestPrints({ prints, limit = 30, loading = false, error = null, onRetry, onSelect, className }: LatestPrintsProps): ReactElement {
  const rows = prints.slice(0, limit);
  const state = loading ? "loading" : error ? "error" : rows.length === 0 ? "empty" : "ready";
  const demo = rows.some((p) => p.data_mode === "demo");

  return (
    <div
      data-testid="pregao-prints"
      data-state={state}
      data-mode={demo ? "demo" : undefined}
      aria-busy={loading ? true : undefined}
      className={cn("grid gap-2", className)}
    >
      <p className="text-xs text-muted">Cotações publicadas pelas casas. Não são negócios fechados.</p>

      {state === "loading" ? (
        <>
          <Skeleton className="h-[22rem]" />
          <span className="sr-only">Carregando…</span>
        </>
      ) : null}

      {state === "error" ? (
        <div role="alert" className="text-sm">
          Não foi possível carregar as atualizações. <span className="text-muted">{error?.message}</span>{" "}
          {onRetry ? (
            <Button variant="outline" size="sm" onClick={onRetry}>
              Tentar de novo
            </Button>
          ) : null}
        </div>
      ) : null}

      {state === "empty" ? <p className="text-sm text-muted">Nenhuma atualização ainda. As casas publicam a cada minuto ou mais.</p> : null}

      {state === "ready" ? (
        <div className="max-h-[22rem] overflow-y-auto">
          <table className="w-full text-[13px]">
            <caption className="sr-only">Últimas atualizações de cotação</caption>
            <thead>
              <tr className="text-muted">
                <th scope="col" className="text-left font-medium">
                  Hora
                </th>
                <th scope="col" className="text-left font-medium">
                  Casa
                </th>
                <th scope="col" className="text-left font-medium">
                  Par
                </th>
                <th scope="col" className="text-right font-medium max-sm:hidden">
                  Compra
                </th>
                <th scope="col" className="text-right font-medium">
                  Venda
                </th>
                <th scope="col" className="text-right font-medium">
                  Δ
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((p) => (
                <tr
                  key={p.id}
                  data-testid="pregao-print-row"
                  data-id={p.id}
                  data-key={p.key}
                  data-kind={p.kind}
                  className="h-8 max-md:h-10 border-t border-border motion-safe:animate-[pregao-flash_1.2s_ease-out_1]"
                >
                  <td className="tnum">
                    <time dateTime={p.captured_at}>{printTime(p.captured_at)}</time>
                  </td>
                  <td>{houseCell(p, onSelect)}</td>
                  <td>{p.pair}</td>
                  <td className="tnum text-right text-foreground max-sm:hidden">{rateText(p.buy, p)}</td>
                  <td className="tnum text-right text-foreground">{rateText(p.sell, p)}</td>
                  <td className="text-right">
                    <Delta value={p.change_pct} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}
