import { FxReveal } from "@/components/ui/fx/fx-reveal";

/** Entrada de cada rota (fade e 4 px, --motion-base). View Transitions fica para a fase 2 (dev/ui/spec-reforma-ui.md §3.5). */
export default function Template({ children }: { children: React.ReactNode }) {
  return <FxReveal>{children}</FxReveal>;
}
