/**
 * Carregamento discreto. Elemento Uiverse «carregador-discreto» (Bodyhc), MIT, Uiverse.io. Anel em passos (steps 12).
 * Dentro do cartão, nunca em tela cheia. Com movimento reduzido o anel fica parado e o texto "Carregando…" informa.
 */
import { cn } from "@/lib/utils";

export function FxSpinner({ label = "Carregando…", className }: { label?: string; className?: string }) {
  return (
    <span role="status" className={cn("inline-flex items-center gap-2 text-caption text-muted", className)}>
      <span aria-hidden className="fx-spin inline-block size-4 rounded-full border-2 border-border border-t-accent" />
      <span>{label}</span>
    </span>
  );
}
