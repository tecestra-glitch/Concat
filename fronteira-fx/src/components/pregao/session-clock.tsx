"use client";
import type { ReactElement } from "react";
import { cn } from "@/lib/utils";

export interface ClockZone {
  id: string;
  label: string;
  tz: string;
}

export const DEFAULT_ZONES: readonly ClockZone[] = [
  { id: "asu", label: "Assunção / CDE", tz: "America/Asuncion" },
  { id: "bsb", label: "Brasília", tz: "America/Sao_Paulo" },
];

const REFERENCE_TZ = "America/Asuncion";
const NO_TIME = "—:—";
const formatters = new Map<string, Intl.DateTimeFormat>();

function formatterFor(tz: string): Intl.DateTimeFormat {
  let formatter = formatters.get(tz);
  if (!formatter) {
    // hourCycle h23 em vez de hour12: false, para a meia-noite nunca virar "24".
    formatter = new Intl.DateTimeFormat("pt-BR", { timeZone: tz, hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
    formatters.set(tz, formatter);
  }
  return formatter;
}

/** Horário "HH:mm" no fuso `tz`. `now === 0` (renderização no servidor) devolve o travessão. */
export function clockText(now: number, tz: string): string {
  if (now === 0) return NO_TIME;
  return formatterFor(tz).format(new Date(now));
}

function referenceText(referenceNext: string | null): string {
  if (!referenceNext) return "sem horário";
  const at = Date.parse(referenceNext);
  if (Number.isNaN(at)) return "sem horário";
  return `próxima às ${clockText(at, REFERENCE_TZ)}`;
}

export interface SessionClockProps {
  now: number;
  zones?: readonly ClockZone[];
  referenceNext?: string | null;
  className?: string;
}

/** Relógios das praças do pregão e a próxima referência do BCP. Puro: o `now` vem de fora. */
export function SessionClock({ now, zones = DEFAULT_ZONES, referenceNext = null, className }: SessionClockProps): ReactElement {
  return (
    <dl data-testid="pregao-clock" className={cn("flex flex-wrap gap-x-4 gap-y-1 text-sm", className)}>
      {zones.map((zone) => (
        <div key={zone.id}>
          <dt className="text-muted">{zone.label}</dt>
          <dd className="tnum" data-tz={zone.tz}>
            {now > 0 ? <time dateTime={new Date(now).toISOString()}>{clockText(now, zone.tz)}</time> : NO_TIME}
          </dd>
        </div>
      ))}
      <div>
        <dt>Referência BCP</dt>
        <dd>{referenceText(referenceNext)}</dd>
      </div>
    </dl>
  );
}
