"use client";
import type { ReactElement } from "react";
import { Badge } from "@/components/ui/badge";
import type { HouseSession, SessionStatus } from "@/lib/pregao/types";
import { cn } from "@/lib/utils";

export interface SessionSummary {
  open: number;
  pre: number;
  closed: number;
  unknown: number;
  total: number;
  nextChangeAt: string | null;
  badge: "gain" | "warn" | "outline";
  label: string;
}

const MINUTE_MS = 60_000;

/** Próxima mudança de status entre as casas (sem referências), depois de `now`. */
function nextChangeAfter(houses: readonly HouseSession[], now: number): string | null {
  let best: string | null = null;
  let bestAt = Infinity;
  for (const house of houses) {
    if (!house.next_change_at) continue;
    const at = Date.parse(house.next_change_at);
    if (at > now && at < bestAt) {
      bestAt = at;
      best = house.next_change_at;
    }
  }
  return best;
}

/** Resumo das casas do pregão. Referências (BCP) ficam fora de todas as contagens. */
export function summarizeSessions(sessions: readonly HouseSession[], now: number): SessionSummary {
  const houses = sessions.filter((session) => !session.reference);
  const countOf = (status: SessionStatus) => houses.filter((session) => session.status === status).length;
  const open = countOf("open");
  const pre = countOf("pre");
  const closed = countOf("closed");
  const unknown = countOf("unknown");

  let badge: SessionSummary["badge"] = "outline";
  let label = "sem horário";
  if (open >= 1) {
    badge = "gain";
    label = "aberto";
  } else if (pre >= 1) {
    badge = "warn";
    label = "pré-abertura";
  } else if (closed >= 1) {
    badge = "outline";
    label = "fechado";
  }

  return {
    open,
    pre,
    closed,
    unknown,
    total: houses.length,
    nextChangeAt: now === 0 ? null : nextChangeAfter(houses, now),
    badge,
    label,
  };
}

/** Tempo até `targetIso`: "N min", "H h MM min" ou "agora" (passado). Minutos arredondados para cima. */
export function formatCountdown(targetIso: string, now: number): string {
  const diff = Date.parse(targetIso) - now;
  if (!(diff > 0)) return "agora";
  const minutes = Math.ceil(diff / MINUTE_MS);
  if (minutes < 60) return `${minutes} min`;
  return `${Math.floor(minutes / 60)} h ${String(minutes % 60).padStart(2, "0")} min`;
}

export interface MarketStatusProps {
  sessions: readonly HouseSession[];
  now: number;
  className?: string;
}

/** Badge com o estado agregado das casas e a próxima mudança. Puro: o `now` vem de fora. */
export function MarketStatus({ sessions, now, className }: MarketStatusProps): ReactElement {
  const summary = summarizeSessions(sessions, now);
  const next = summary.nextChangeAt ? ` · próxima mudança em ${formatCountdown(summary.nextChangeAt, now)}` : "";
  return (
    <p data-testid="pregao-market-status" data-badge={summary.badge} className={cn("flex items-center gap-2 text-sm", className)}>
      <Badge variant={summary.badge}>{summary.label}</Badge>
      <span>{`${summary.open} de ${summary.total} casas abertas${next}`}</span>
    </p>
  );
}
