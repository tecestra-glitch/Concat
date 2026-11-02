import { Inbox, SearchX, Unplug } from "lucide-react";
import { cn } from "@/lib/utils";

export type EmptyKind = "no-data" | "no-match" | "source-down";

const DEFAULTS: Record<EmptyKind, { icon: typeof Inbox; title: string; description: string }> = {
  "no-data": { icon: Inbox, title: "Sem dados para este contexto", description: "Nada foi coletado ainda. Quando houver registros, eles aparecem aqui." },
  "no-match": { icon: SearchX, title: "Nenhum resultado para os filtros", description: "Amplie a cidade, a moeda ou a fonte para ver mais linhas." },
  "source-down": { icon: Unplug, title: "Fonte fora do ar", description: "A última coleta falhou; os valores anteriores ficam marcados como antigos." },
};

/** DS11: três tipos de vazio, cada um explicando o que fazer, sem tom emocional. */
export function EmptyState({ kind = "no-data", title, description, action, className, compact = false }: { kind?: EmptyKind; title?: string; description?: string; action?: React.ReactNode; className?: string; compact?: boolean }) {
  const d = DEFAULTS[kind];
  const Icon = d.icon;
  return (
    <div className={cn("flex flex-col items-center justify-center text-center text-sm text-muted", compact ? "gap-1 p-4" : "gap-2 p-8", className)} data-empty={kind}>
      <Icon className="size-5 opacity-70" aria-hidden />
      <p className="font-medium text-foreground">{title ?? d.title}</p>
      <p className="max-w-prose text-xs">{description ?? d.description}</p>
      {action}
    </div>
  );
}
