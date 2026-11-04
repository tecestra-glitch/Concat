"use client";
import type { ReactElement } from "react";
import { Badge } from "@/components/ui/badge";
import type { HouseSession, SessionStatus } from "@/lib/pregao/types";
import { cn } from "@/lib/utils";

export interface SessionSummary {
  /** Casas físicas (sem referências e sem canal digital): contagem por status. */
  open: number;
  pre: number;
  closed: number;
  unknown: number;
  total: number;
  /** Casas digitais, à parte: nunca entram no selo "aberto" nem na contagem física. */
  digitalOpen: number;
  digitalTotal: number;
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

/**
 * Resumo das casas do pregão. Referências (BCP) ficam fora de todas as contagens. O selo "aberto" (verde) só vale
 * para casa física aberta: digitais abertas com todas as físicas fechadas dão "só digitais" neutro.
 */
export function summarizeSessions(sessions: readonly HouseSession[], now: number): SessionSummary {
  const houses = sessions.filter((session) => !session.reference);
  const physical = houses.filter((session) => session.channel !== "digital");
  const digital = houses.filter((session) => session.channel === "digital");
  const countOf = (list: readonly HouseSession[], status: SessionStatus) => list.filter((session) => session.status === status).length;
  const open = countOf(physical, "open");
  const pre = countOf(physical, "pre");
  const closed = countOf(physical, "closed");
  const unknown = countOf(physical, "unknown");
  const digitalOpen = countOf(digital, "open");

  let badge: SessionSummary["badge"] = "outline";
  let label = "sem horário";
  if (open >= 1) {
    badge = "gain";
    label = "aberto";
  } else if (pre >= 1) {
    badge = "warn";
    label = "pré-abertura";
  } else if (digitalOpen >= 1) {
    badge = "outline";
    label = "só digitais";
  } else if (closed >= 1) {
    badge = "outline";
    label = "fechado";
  }

  return {
    open,
    pre,
    closed,
    unknown,
    total: physical.length,
    digitalOpen,
    digitalTotal: digital.length,
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
  /** Enquanto as cotações do par carregam, as casas do par ainda não são conhecidas: não se afirma nada. */
  loading?: boolean;
  className?: string;
}

/** Badge com o estado agregado das casas e a próxima mudança. Puro: o `now` vem de fora. */
export function MarketStatus({ sessions, now, loading = false, className }: MarketStatusProps): ReactElement {
  if (loading) {
    return (
      <p data-testid="pregao-market-status" data-badge="outline" className={cn("text-sm text-muted", className)}>
        Carregando horários…
      </p>
    );
  }
  const summary = summarizeSessions(sessions, now);
  const parts: string[] = [];
  if (summary.total > 0) parts.push(`${summary.open} de ${summary.total} casas físicas abertas`);
  if (summary.digitalTotal > 0) parts.push(`${summary.digitalOpen} de ${summary.digitalTotal} digitais abertas`);
  if (parts.length === 0) parts.push("nenhuma casa com horário informado");
  const next = summary.nextChangeAt ? ` · próxima mudança em ${formatCountdown(summary.nextChangeAt, now)}` : "";
  return (
    <p data-testid="pregao-market-status" data-badge={summary.badge} className={cn("flex items-center gap-2 text-sm", className)}>
      <Badge variant={summary.badge}>{summary.label}</Badge>
      <span>{`${parts.join(" · ")}${next}`}</span>
    </p>
  );
}
