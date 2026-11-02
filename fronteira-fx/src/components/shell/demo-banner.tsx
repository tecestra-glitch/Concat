"use client";
import { useSettings } from "@/lib/settings";
import { useBackendHealth } from "@/lib/queries";

/**
 * Faixa de modo (D3): «Demonstração» quando o modo resolvido é demo ou quando o backend se declara em
 * demo; «Simulação» quando as consultas viajam com data_mode=simulation. Em modo real não há faixa.
 */
export function DemoBanner() {
  const { mode } = useSettings();
  const health = useBackendHealth();
  const demo = mode === "demo" || health.data?.data_mode === "demo";
  if (demo) {
    return (
      <div role="status" data-testid="demo-banner" className="flex items-center justify-center gap-2 border-b border-warn/40 bg-warn/15 px-3 py-1.5 text-center text-xs font-medium text-warn">
        <span aria-hidden>▲</span>
        Demonstração — dados ilustrativos. Nenhuma cotação aqui é atual ou executável.
      </div>
    );
  }
  if (mode === "simulation") {
    return (
      <div role="status" data-testid="simulation-banner" className="flex items-center justify-center gap-2 border-b border-accent/40 bg-accent/10 px-3 py-1.5 text-center text-xs font-medium text-accent">
        <span aria-hidden>◆</span>
        Simulação — cotações reais, resultados gravados à parte (data_mode=simulation). Nada é executado.
      </div>
    );
  }
  return null;
}
