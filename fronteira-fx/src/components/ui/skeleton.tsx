import { FxSkeleton } from "./fx/fx-skeleton";

/** Esqueleto padrão do app: brilho em `.fx-skeleton` (substitui o `animate-pulse`). Movimento reduzido: bloco estático. */
export function Skeleton(props: React.HTMLAttributes<HTMLDivElement>) {
  return <FxSkeleton {...props} />;
}
