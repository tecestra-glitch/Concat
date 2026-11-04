import { Bot, MapPin, Smartphone } from "lucide-react";
import type { RouteChannel } from "@/lib/api/types";
import { CHANNEL_TEXT } from "./cycle-helpers";
import { cn } from "@/lib/utils";

const SHORT: Record<RouteChannel, string> = { presencial: "Presencial", assistida: "Assistida", automatizavel: "Automatizável" };
const ICON = { presencial: MapPin, assistida: Smartphone, automatizavel: Bot } as const;

/** Canal de uma perna com ícone e texto (nunca só cor): presencial, assistida ou automatizável. */
export function LegChannel({ channel, className }: { channel: RouteChannel; className?: string }) {
  const Icon = ICON[channel];
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-sm border border-border px-1.5 py-0.5 text-xs text-foreground", className)} title={CHANNEL_TEXT[channel]} data-channel={channel}>
      <Icon className="size-3.5 shrink-0" aria-hidden />
      {SHORT[channel]}
    </span>
  );
}
