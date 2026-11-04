import { Skeleton } from "./skeleton";
import { cn } from "@/lib/utils";

/** DS11: linhas de esqueleto com atraso escalonado; anunciado como «Carregando». */
export function TableSkeleton({ rows = 5, cols = 4, className, label = "Carregando" }: { rows?: number; cols?: number; className?: string; label?: string }) {
  return (
    <div role="status" aria-label={label} className={cn("stagger grid gap-2 p-3", className)}>
      <span className="sr-only">Carregando…</span>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="grid gap-2" style={{ "--i": i, gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` } as React.CSSProperties}>
          {Array.from({ length: cols }, (_, j) => (
            <Skeleton key={j} className={cn("h-5", j === 0 && "w-3/4")} />
          ))}
        </div>
      ))}
    </div>
  );
}
