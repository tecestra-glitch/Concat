"use client";
import type { ReactElement } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { CITY_LABEL } from "@/lib/api/types";
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
const TIME_SHORT = new Intl.DateTimeFormat("pt-BR", { timeZone: TZ, hour: "2-digit", minute: "2-digit", hourCycle: "h23" });

/** Hora HH:mm:ss no fuso de exibição da tela. */
export function printTime(iso: string): string {
  return TIME.format(new Date(iso));
}

/** Hora HH:mm no fuso de exibição da tela (coluna estreita; os segundos ficam no `title`). */
export function printTimeShort(iso: string): string {
  return TIME_SHORT.format(new Date(iso));
}

/** Par e cidade da filial ("USD/PYG · CDE"); digital fica só com o par. */
export function printSubtitle(p: Pick<Print, "pair" | "city">): string {
  return p.city ? `${p.pair} · ${p.city}` : p.pair;
}

function rateText(value: string | null, p: Print): string {
  const text = formatRate(value, quoteOfPair(p.pair));
  return p.kind === "market_reference" && value !== null ? `≈ ${text}` : text;
}

/**
 * Nome da casa numa linha só (`truncate`, nome inteiro e cidade no `title`) e, embaixo, o par e a cidade
 * quando a coluna Par está oculta (painel estreito), com o selo "incompleta" ao lado deles. Na linha do nome o
 * selo fica só quando há espaço (`@md`). O nome nunca empurra as colunas de preço para fora.
 */
function houseCell(p: Print, onSelect?: (key: string) => void): ReactElement {
  const isRef = p.kind === "market_reference";
  const title = p.city ? `${p.house} · ${CITY_LABEL[p.city]}` : p.house;
  const nameClass = "block min-w-0 truncate";
  const name =
    onSelect && !isRef ? (
      <button
        type="button"
        title={title}
        onClick={() => onSelect(p.key)}
        className={cn(
          nameClass,
          "max-w-full rounded-sm text-left underline-offset-2 hover:underline focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2",
        )}
      >
        {p.house}
      </button>
    ) : (
      <span title={title} className={nameClass}>
        {p.house}
      </span>
    );
  return (
    <span className="flex min-w-0 flex-col">
      <span className="flex min-w-0 items-center gap-1">
        {name}
        {p.city ? (
          <span className="shrink-0 whitespace-nowrap text-xs text-muted @max-md:hidden">
            · {p.city}
          </span>
        ) : null}
        {isRef ? <ReferenceBadge compact /> : null}
        {p.incomplete ? (
          <Badge variant="warn" className="@max-md:hidden">
            incompleta
          </Badge>
        ) : null}
      </span>
      {/* Painel estreito: o selo "incompleta" desce para a linha do par · cidade e o nome da casa fica inteiro; sem
          espaço ao lado do subtítulo, o selo quebra para baixo dele (nada é cortado). */}
      <span className="flex min-w-0 flex-wrap items-center gap-x-1 @md:hidden">
        <span data-testid="pregao-print-sub" className="truncate text-[11px] text-muted">
          {printSubtitle(p)}
        </span>
        {p.incomplete ? (
          <Badge variant="warn" className="shrink-0">
            incompleta
          </Badge>
        ) : null}
      </span>
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
      className={cn("flex flex-col gap-2", className)}
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
        /* Consulta de contêiner: em xl o painel tem 18rem. Abaixo de @md (28rem) o par e a cidade viram
           subtítulo da casa, a variação desce para baixo da venda e a hora perde os segundos (que ficam no
           title); a rolagem nos dois eixos é só a rede de segurança. Em xl o painel vai até o fim do livro:
           sem teto de altura, a tabela ocupa o que sobra (flex-1) e rola dentro. Abaixo de md (aba Últimas do
           celular) também não há teto: a página rola sozinha, sem rolagem dentro da rolagem. */
        <div className="@container relative min-h-0 flex-1 overflow-auto md:max-h-[22rem] xl:max-h-none">
          <table className="w-full text-[12px] @md:text-[13px] [&_td]:px-1 [&_th]:px-1 [&_td:first-child]:pl-0 [&_th:first-child]:pl-0 [&_td:last-child]:pr-0 [&_th:last-child]:pr-0">
            <caption className="sr-only">Últimas atualizações de cotação</caption>
            <thead>
              <tr className="text-muted">
                <th scope="col" className="text-left font-medium">
                  Hora
                </th>
                <th scope="col" className="w-full text-left font-medium">
                  Casa
                </th>
                <th scope="col" className="text-left font-medium @max-md:hidden">
                  Par
                </th>
                <th scope="col" className="text-right font-medium max-sm:hidden">
                  Compra
                </th>
                <th scope="col" className="whitespace-nowrap text-right font-medium">
                  Venda
                  <span className="@md:hidden">
                    <span aria-hidden> · Δ</span>
                    <span className="sr-only"> e variação</span>
                  </span>
                </th>
                <th scope="col" className="text-right font-medium @max-md:hidden">
                  <span aria-hidden>Δ</span>
                  <span className="sr-only">Variação</span>
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
                  <td className="tnum whitespace-nowrap">
                    <time dateTime={p.captured_at} title={printTime(p.captured_at)}>
                      <span className="@max-md:hidden">{printTime(p.captured_at)}</span>
                      <span className="@md:hidden">{printTimeShort(p.captured_at)}</span>
                    </time>
                  </td>
                  <td className="max-w-0">{houseCell(p, onSelect)}</td>
                  <td className="whitespace-nowrap @max-md:hidden">{p.pair}</td>
                  <td className="tnum whitespace-nowrap text-right text-foreground max-sm:hidden">{rateText(p.buy, p)}</td>
                  <td className="tnum whitespace-nowrap text-right text-foreground">
                    {rateText(p.sell, p)}
                    <span className="block text-[11px] @md:hidden">
                      <Delta value={p.change_pct} />
                    </span>
                  </td>
                  <td className="whitespace-nowrap text-right @max-md:hidden">
                    <Delta value={p.change_pct} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {/* md–lg: com o teto de 22rem a última linha visível sai cortada ao meio; o degradê no rodapé do scroller
              assume o corte e avisa que a lista continua. No fim da rolagem ele fica abaixo da tabela, sem cobrir nada. */}
          <div
            aria-hidden
            data-testid="pregao-prints-fade"
            className="pointer-events-none sticky bottom-0 left-0 hidden h-8 bg-linear-to-t from-background to-transparent md:block xl:hidden"
          />
        </div>
      ) : null}
    </div>
  );
}
