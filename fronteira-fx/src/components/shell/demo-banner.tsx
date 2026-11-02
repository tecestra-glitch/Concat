"use client";
import { useSettings } from "@/lib/settings";

export function DemoBanner() {
  const { mode } = useSettings();
  if (mode !== "demo") return null;
  return (
    <div role="status" data-testid="demo-banner" className="flex items-center justify-center gap-2 border-b border-warn/40 bg-warn/15 px-3 py-1.5 text-xs font-medium text-warn">
      <span aria-hidden>▲</span>
      Demonstração — dados ilustrativos. Nenhuma cotação aqui é atual ou executável.
    </div>
  );
}
