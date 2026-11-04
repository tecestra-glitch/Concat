/**
 * Cartão com barra de progresso. Elemento Uiverse «cartao-progresso» (Cybercom682), MIT, Uiverse.io. A barra não
 * tem transição de largura (regra do app: número que muda não se move; só realce curto). Criado na fase 1; uso na
 * fase 2 (coleta por fonte em Fontes).
 */
import { cn } from "@/lib/utils";
import { FxCard } from "./fx-card";

export interface FxProgressCardProps {
  title: string;
  /** Fração entre 0 e 1 (ex.: 0,4 = 40 %). Valores fora do intervalo são limitados. */
  value: number;
  detail?: string;
  className?: string;
}

export function FxProgressCard({ title, value, detail, className }: FxProgressCardProps) {
  const pct = Math.round(Math.min(1, Math.max(0, Number.isFinite(value) ? value : 0)) * 100);
  return (
    <FxCard className={cn("grid gap-2 p-4", className)}>
      <div className="flex items-baseline justify-between gap-2 text-body">
        <span className="font-medium">{title}</span>
        <span className="fx-num">{pct} %</span>
      </div>
      <div role="progressbar" aria-label={title} aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct} className="h-2 overflow-hidden rounded-chip bg-surface-3">
        <div className="h-full bg-accent" style={{ width: `${pct}%` }} />
      </div>
      {detail && <p className="text-caption text-muted">{detail}</p>}
    </FxCard>
  );
}
