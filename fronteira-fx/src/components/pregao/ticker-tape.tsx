"use client";
import type { CSSProperties, ReactElement } from "react";
import { Pause, Play, TriangleAlert } from "lucide-react";
import { Delta } from "@/components/pregao/delta";
import { ReferenceBadge } from "@/components/pregao/reference-badge";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { formatRate } from "@/lib/format";
import { quoteOfPair } from "@/lib/pregao/candles";
import { PAIR_LABEL, type TickerItem } from "@/lib/pregao/types";
import { cn } from "@/lib/utils";

export interface TickerTapeProps {
  items: TickerItem[];
  selectedKey?: string | null;
  onSelect?: (key: string) => void;
  /** Segundos por volta do laço; padrão 40. */
  durationS?: number;
  loading?: boolean;
  /** Fita parada pelo botão "Pausar fita" (preferência `tapePaused`). */
  paused?: boolean;
  /** Sem handler, o botão não aparece (a fita só pausa com hover/foco). */
  onPausedChange?: (paused: boolean) => void;
  className?: string;
}

/** Rótulo acessível de um item: "USD/PYG Cambios Chaco 7.335" (mid nulo → "—"). */
export function tickerLabel(item: TickerItem): string {
  return `${PAIR_LABEL[item.pair]} ${item.house} ${formatRate(item.mid, quoteOfPair(item.pair))}`;
}

interface TickerTapeItemProps {
  item: TickerItem;
  selected: boolean;
  onSelect?: (key: string) => void;
  /** Cópia de laço: escondida de leitores de tela e fora da ordem de tabulação. */
  dup: boolean;
}

function TickerTapeItem({ item, selected, onSelect, dup }: TickerTapeItemProps): ReactElement {
  const isReference = item.kind === "market_reference";
  const value = (
    <>
      <span className={cn("font-medium", selected && "text-accent")}>{PAIR_LABEL[item.pair]}</span>
      <span className="text-muted">{item.house}</span>
      <span className="tnum">
        {isReference ? "≈ " : null}
        {formatRate(item.mid, quoteOfPair(item.pair))}
        {isReference ? <ReferenceBadge compact source={item.source_id} className="ml-1" /> : null}
      </span>
    </>
  );

  return (
    <li
      data-testid="pregao-ticker-item"
      data-key={item.key}
      data-kind={item.kind}
      aria-hidden={dup ? "true" : undefined}
      data-dup={dup ? "true" : undefined}
      className={cn("flex items-center gap-2 whitespace-nowrap", dup && "motion-reduce:hidden")}
    >
      {isReference || !onSelect ? (
        <span className="inline-flex items-center gap-2">{value}</span>
      ) : (
        <button
          type="button"
          aria-label={tickerLabel(item)}
          aria-current={selected ? "true" : undefined}
          tabIndex={dup ? -1 : undefined}
          onClick={() => onSelect(item.key)}
          className="inline-flex min-h-10 items-center gap-2 rounded-sm md:min-h-8 focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2"
        >
          {value}
        </button>
      )}
      <Delta value={item.change_pct} />
      {item.incomplete ? (
        <Badge variant="warn">
          <TriangleAlert size={12} aria-hidden />
          <span className="sr-only">cotação incompleta</span>
        </Badge>
      ) : null}
    </li>
  );
}

export interface TapePauseButtonProps {
  paused: boolean;
  onPausedChange: (paused: boolean) => void;
}

/**
 * Botão visível de pausa (WCAG 2.2.2): no toque não existe hover nem foco para parar a fita. Botão de alternância
 * (`aria-pressed`) com o rótulo da ação. Com movimento reduzido a fita já é estática e o botão some.
 */
export function TapePauseButton({ paused, onPausedChange }: TapePauseButtonProps): ReactElement {
  const Icon = paused ? Play : Pause;
  return (
    <button
      type="button"
      data-testid="pregao-ticker-pause"
      aria-pressed={paused}
      onClick={() => onPausedChange(!paused)}
      className="inline-flex min-h-10 shrink-0 items-center gap-1 border-l border-border bg-surface px-2 text-xs text-muted hover:text-foreground motion-reduce:hidden md:min-h-8 focus-visible:outline-2 focus-visible:outline-ring focus-visible:-outline-offset-2"
    >
      <Icon size={12} aria-hidden />
      {paused ? "Retomar fita" : "Pausar fita"}
    </button>
  );
}

/**
 * Fita rolante com a última cotação de cada série. O conteúdo é repetido para o laço contínuo;
 * a cópia é escondida de leitores de tela. Sem `aria-live`: a fita muda a cada minuto (§0.14).
 */
export function TickerTape({
  items,
  selectedKey = null,
  onSelect,
  durationS = 40,
  loading = false,
  paused = false,
  onPausedChange,
  className,
}: TickerTapeProps): ReactElement {
  const state = loading ? "loading" : items.length === 0 ? "empty" : "ready";
  const demo = items.some((i) => i.data_mode === "demo");

  return (
    <div
      role="region"
      aria-label="Fita de cotações"
      data-testid="pregao-ticker"
      data-state={state}
      data-mode={demo ? "demo" : undefined}
      aria-busy={loading ? "true" : undefined}
      className={cn("flex items-stretch overflow-hidden border-y border-border bg-surface", className)}
    >
      {state === "loading" ? (
        <>
          <Skeleton className="h-8 w-full" />
          <span className="sr-only">Carregando…</span>
        </>
      ) : state === "empty" ? (
        <p className="text-sm text-muted">Sem cotações na fita.</p>
      ) : (
        <>
          <div className="min-w-0 flex-1 overflow-hidden">
            <ul
              data-paused={paused ? "true" : undefined}
              className={cn(
                "pregao-marquee flex w-max gap-6 py-1.5 text-[13px] motion-reduce:w-full motion-reduce:flex-wrap motion-reduce:animate-none",
                paused && "[animation-play-state:paused]",
              )}
              style={{ "--tape-duration": `${durationS}s` } as CSSProperties}
            >
              {items.map((item) => (
                <TickerTapeItem key={item.key} item={item} selected={item.key === selectedKey} onSelect={onSelect} dup={false} />
              ))}
              {items.map((item) => (
                <TickerTapeItem key={`dup:${item.key}`} item={item} selected={item.key === selectedKey} onSelect={onSelect} dup />
              ))}
            </ul>
          </div>
          {onPausedChange ? <TapePauseButton paused={paused} onPausedChange={onPausedChange} /> : null}
        </>
      )}
    </div>
  );
}
