import type { Source } from "./types";

/**
 * País de uma fonte, para a bandeira na UI (dev/ui/spec-reforma-ui.md, seção 5, item d).
 * `Source` ainda não tem campo de país no contrato (entra na fase 2); até lá a regra deriva pela cobertura:
 * - alguma cidade de CDE, ASU ou PJC (todas no Paraguai) → "PY";
 * - sem cidade e moeda só PYG → "PY";
 * - caso contrário → `null` (a UI mostra "país não informado", sem bandeira).
 */
export type SourceCountry = "PY" | "BR" | "US" | "AR" | "EU" | null;

const PY_CITIES = new Set<string>(["CDE", "ASU", "PJC"]);

export function sourceCountry(source: Pick<Source, "coverage">): SourceCountry {
  const cities = source.coverage?.cities ?? [];
  const currencies = source.coverage?.currencies ?? [];
  if (cities.some((c) => PY_CITIES.has(c))) return "PY";
  if (cities.length === 0 && currencies.length > 0 && currencies.every((c) => c === "PYG")) return "PY";
  return null;
}

/** Rótulo do país para a tela (texto ao lado da bandeira; sem país, o texto é "país não informado"). */
export const COUNTRY_LABEL: Record<Exclude<SourceCountry, null>, string> = {
  PY: "Paraguai",
  BR: "Brasil",
  US: "Estados Unidos",
  AR: "Argentina",
  EU: "União Europeia",
};
