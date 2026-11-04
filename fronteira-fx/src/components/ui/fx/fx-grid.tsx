/**
 * Fundo em grade sutil. Elemento Uiverse «padrao-grade» (adamgiebl), MIT, Uiverse.io. Linhas com --grid-line; é
 * decorativo (aria-hidden, pointer-events: none) e precisa de um pai com `position: relative`.
 * Crédito Uiverse.io: slug `padrao-grade`; elemento adamgiebl_curvy-earwig-79; autor adamgiebl; licença MIT; link https://uiverse.io/adamgiebl/curvy-earwig-79
 * Texto completo da licença: docs/creditos-uiverse.md.
 */
import { cn } from "@/lib/utils";

export function FxGrid({ className }: { className?: string }) {
  return <div aria-hidden="true" className={cn("pointer-events-none absolute inset-0 fx-grid", className)} />;
}
