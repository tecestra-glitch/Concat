"use client";
import { useLive } from "@/lib/live";
import { cn } from "@/lib/utils";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { formatAge } from "@/lib/format";
import { useNow } from "@/lib/use-now";

const LABEL = {
  connecting: "Conectando…",
  connected: "Conectado",
  scheduled: "Ao vivo · atualiza a cada 30 s",
  reconnecting: "Reconectando…",
  offline: "Offline",
  demo: "Demonstração",
} as const;

export function ConnectionStatus() {
  const { state, lastEventAt, eventsReceived } = useLive();
  const now = useNow();
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <output
          data-testid="connection-status"
          data-state={state}
          data-volatile
          className="inline-flex h-8 items-center gap-2 rounded-md border border-border bg-surface px-2.5 text-xs"
          aria-live="polite"
        >
          <span
            aria-hidden
            className={cn(
              "size-2 rounded-full",
              (state === "connected" || state === "scheduled") && "bg-gain",
              (state === "reconnecting" || state === "connecting") && "bg-warn",
              state === "offline" && "bg-loss",
              state === "demo" && "bg-warn",
            )}
          />
          <span className="font-medium">{LABEL[state]}</span>
        </output>
      </TooltipTrigger>
      <TooltipContent>
        Estado da conexão em tempo real (SSE). A idade de cada cotação é mostrada separadamente nas tabelas.
        {state !== "demo" && (
          <>
            <br />Último evento: {now === 0 ? "…" : formatAge(lastEventAt, now)} · {eventsReceived} eventos
          </>
        )}
      </TooltipContent>
    </Tooltip>
  );
}
