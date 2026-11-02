"use client";
import { useSettings } from "@/lib/settings";
import { useBackendHealth } from "@/lib/queries";
import { modeConflict } from "@/lib/api/client";
import type { Mode } from "@/lib/api/types";

const NAME: Record<Mode, string> = { real: "Real", simulation: "Simulação", demo: "Demonstração" };

/**
 * Faixa de modo (D3 / SEC-01): «Demonstração» quando o modo resolvido é demo; «Modo em conflito» quando a
 * preferência pede um modo que a instância do backend não serve (as chamadas são recusadas com 409, nada é
 * lido nem gravado); «Simulação» só quando a própria instância serve data_mode=simulation. Em modo real
 * alinhado não há faixa.
 */
export function DemoBanner() {
  const { mode, backendMode } = useSettings();
  const health = useBackendHealth();
  const instance = health.data?.data_mode ?? backendMode;
  if (mode === "demo") {
    return (
      <div role="status" data-testid="demo-banner" className="flex items-center justify-center gap-2 border-b border-warn/40 bg-warn/15 px-3 py-1.5 text-center text-xs font-medium text-warn">
        <span aria-hidden>▲</span>
        Demonstração — dados ilustrativos. Nenhuma cotação aqui é atual ou executável.
      </div>
    );
  }
  if (modeConflict(mode, instance)) {
    return (
      <div role="alert" data-testid="mode-conflict-banner" className="flex items-center justify-center gap-2 border-b border-loss/40 bg-loss/10 px-3 py-1.5 text-center text-xs font-medium text-loss">
        <span aria-hidden>■</span>
        Modo em conflito — o backend serve «{NAME[instance as Mode]}» e a preferência é «{NAME[mode]}». Nada é lido nem gravado até alinhar em Configurações.
      </div>
    );
  }
  if (mode === "simulation") {
    return (
      <div role="status" data-testid="simulation-banner" className="flex items-center justify-center gap-2 border-b border-accent/40 bg-accent/10 px-3 py-1.5 text-center text-xs font-medium text-accent">
        <span aria-hidden>◆</span>
        Simulação — instância à parte do backend (data_mode=simulation); nada toca os dados reais e nada é executado.
      </div>
    );
  }
  return null;
}
