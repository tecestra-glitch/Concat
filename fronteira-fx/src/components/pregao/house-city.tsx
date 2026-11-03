import type { ReactElement } from "react";
import { CITY_LABEL, type City } from "@/lib/api/types";
import { cn } from "@/lib/utils";

export interface HouseCityProps {
  city: City;
  /** `data-testid` do selo; o livro usa `pregao-book-city`, a lista `pregao-watchlist-city`. */
  testId?: string;
  className?: string;
}

/**
 * Cidade da filial com a sigla usada no resto do app (CDE, ASU, PJC); o nome inteiro fica no `title` e para leitor
 * de tela num nó só: a sigla é `aria-hidden` e o leitor lê apenas "Ciudad del Este" (não "CDE , Ciudad del Este").
 * A mesma casa aparece uma vez por filial: sem a cidade, "Cambios Chaco" pareceria duplicada. Digital: nada.
 */
export function HouseCity({ city, testId = "pregao-book-city", className }: HouseCityProps): ReactElement | null {
  if (city === null) return null;
  return (
    <span data-testid={testId} className={cn("whitespace-nowrap text-xs font-normal text-muted", className)} title={CITY_LABEL[city]}>
      <span aria-hidden>{city}</span>
      <span className="sr-only">{CITY_LABEL[city]}</span>
    </span>
  );
}
