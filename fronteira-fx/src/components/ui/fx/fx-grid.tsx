/**
 * Fundo em grade sutil. Elemento Uiverse «padrao-grade» (adamgiebl), MIT, Uiverse.io. Linhas com --grid-line; é
 * decorativo (aria-hidden, pointer-events: none) e precisa de um pai com `position: relative`.
 */
import { cn } from "@/lib/utils";

export function FxGrid({ className }: { className?: string }) {
  return <div aria-hidden="true" className={cn("pointer-events-none absolute inset-0 fx-grid", className)} />;
}
