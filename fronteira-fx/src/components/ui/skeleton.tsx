/**
 * Crédito Uiverse.io: slug `esqueleto-shimmer`; elemento arshshaikh06_purple-sheep-4; autor arshshaikh06; licença MIT; link https://uiverse.io/arshshaikh06/purple-sheep-4
 * Texto completo da licença: docs/creditos-uiverse.md.
 */
import { FxSkeleton } from "./fx/fx-skeleton";

/** Esqueleto padrão do app: brilho em `.fx-skeleton` (substitui o `animate-pulse`). Movimento reduzido: bloco estático. */
export function Skeleton(props: React.HTMLAttributes<HTMLDivElement>) {
  return <FxSkeleton {...props} />;
}
