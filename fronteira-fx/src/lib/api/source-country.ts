import type { Source } from "./types";

/**
 * País de uma fonte, para a bandeira na UI (dev/ui/spec-reforma-ui.md, seção 5, item d).
 * `Source` ainda não tem campo de país no contrato (entra na fase 2). Até lá a regra é, nesta ordem:
 * 1. mapa explícito por `source.id` para as fontes paraguaias conhecidas (BCP, banco demo PY, casas e bancos);
 * 2. alguma cidade de CDE, ASU ou PJC (todas no Paraguai) → "PY";
 * 3. caso contrário → `null` (a UI mostra "país não informado", sem bandeira).
 * A moeda NÃO é sinal: remessadoras com PYG (ex.: Western Union, BRL/PYG) não viram paraguaias.
 * Novos bancos paraguaios (Basa, Familiar, GNB e outros) entram neste mapa quando o backend os devolver com o id.
 */
export type SourceCountry = "PY" | "BR" | "US" | "AR" | "EU" | null;

/** Fontes paraguaias por id (dados do backend e da demonstração). Sem id conhecido, sem bandeira. */
export const PY_SOURCE_IDS: ReadonlySet<string> = new Set<string>([
  "bcp",
  "banco-demo-py",
  "alberdi",
  "bonanza",
  "chaco",
  "maxicambios",
  "myd",
  "norte",
]);

const PY_CITIES = new Set<string>(["CDE", "ASU", "PJC"]);

export function sourceCountry(source: Pick<Source, "id" | "coverage">): SourceCountry {
  if (PY_SOURCE_IDS.has(source.id)) return "PY";
  const cities = source.coverage?.cities ?? [];
  if (cities.some((c) => PY_CITIES.has(c))) return "PY";
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
