/**
 * Derivações da tela de pregão que não dependem das consultas de resumo (§24.4): níveis por par,
 * série escolhida, chaves para o resumo e as miniaturas, casas do mapa de calor, linha de
 * referência do gráfico e pernas do cruzamento. Puro: o container (`pregao.tsx`) só liga os hooks.
 * Referências (BCP, dolarPy) nunca são série padrão nem perna de cruzamento.
 */
import type { Quote, Source } from "@/lib/api/types";
import { legOf, type Leg } from "./cross";
import { defaultKeyFor, houseName, refMidFor, toBookLevels } from "./derive";
import { quoteKey } from "./keys";
import { pairKeyOf } from "./candles";
import { PAIRS, type BookLevel, type HouseSession, type PairKey } from "./types";

const REF_MAX_AGE_MS = 24 * 3600 * 1000;
const REF_PRIORITY: Record<string, number> = { bcp: 0, dolarpy: 1 };

export interface PregaoViewInput {
  quotes: Quote[];
  sources: Source[];
  sessions: HouseSession[];
  pair: PairKey;
  selectedKey: string | null;
  now: Date;
}

export interface PregaoReference {
  value: string;
  label: string;
}

export interface PregaoCross {
  house: string;
  usdPyg: Leg | null;
  usdBrl: Leg | null;
  direct: Leg | null;
}

export interface PregaoView {
  levelsByPair: Record<PairKey, BookLevel[]>;
  levels: BookLevel[];
  allLevels: BookLevel[];
  /** Casas e referências de todos os pares, sem repetição: alimentam `/v1/pregao/stats`. */
  allKeys: string[];
  /** Casas do par atual: alimentam as miniaturas da lista. */
  houseKeys: string[];
  effectiveKey: string | null;
  selectedLevel: BookLevel | null;
  heatHouses: { source_id: string; house: string }[];
  reference: PregaoReference | null;
  cross: PregaoCross;
  referenceNext: string | null;
}

const isRef = (l: { kind: Quote["kind"] }) => l.kind === "market_reference";
const stripDemo = (id: string) => (id.startsWith("demo-") ? id.slice(5) : id);
/** Segmento `[3]` da chave (`fonte:cidade:PAR:modalidade…`). */
const modalityOf = (key: string) => key.split(":")[3] ?? "";

/** Próximo par na sequência de `PAIRS`, dando a volta nos dois sentidos. */
export function cyclePair(pair: PairKey, dir: 1 | -1): PairKey {
  const i = PAIRS.indexOf(pair);
  return PAIRS[(i + dir + PAIRS.length) % PAIRS.length];
}

/** Linha de referência do gráfico: o mesmo `mid` de `refMidFor`, com o nome da fonte que o deu. */
function referenceFor(quotes: Quote[], sources: Source[], pair: PairKey, now: Date): PregaoReference | null {
  const mid = refMidFor(quotes, pair, now);
  if (mid === null) return null;
  const freshAfter = now.getTime() - REF_MAX_AGE_MS;
  let sourceId: string | null = null;
  let bestRank = Number.POSITIVE_INFINITY;
  for (const q of quotes) {
    if (q.kind !== "market_reference" || pairKeyOf(quoteKey(q)) !== pair) continue;
    const at = Date.parse(q.captured_at);
    if (Number.isNaN(at) || at < freshAfter) continue;
    const rank = REF_PRIORITY[stripDemo(q.source_id)] ?? 2;
    if (rank < bestRank) {
      bestRank = rank;
      sourceId = q.source_id;
    }
  }
  return { value: String(mid), label: `≈ ${sourceId === null ? "referência" : houseName(sources, sourceId)}` };
}

/** Pernas do cruzamento na mesma casa, cidade e modalidade da casa base (contexto não se mistura). */
function crossFor(levelsByPair: Record<PairKey, BookLevel[]>, base: BookLevel | null): PregaoCross {
  if (base === null) return { house: "—", usdPyg: null, usdBrl: null, direct: null };
  const same = (l: BookLevel) => !isRef(l) && l.source_id === base.source_id && l.city === base.city && modalityOf(l.key) === modalityOf(base.key);
  return {
    house: base.house,
    usdPyg: legOf(levelsByPair["USD/PYG"].find(same)),
    usdBrl: legOf(levelsByPair["USD/BRL"].find(same)),
    direct: legOf(levelsByPair["BRL/PYG"].find(same)),
  };
}

export function buildPregaoView({ quotes, sources, sessions, pair, selectedKey, now }: PregaoViewInput): PregaoView {
  const levelsByPair = Object.fromEntries(PAIRS.map((p) => [p, toBookLevels(quotes, p, sources, sessions, now)])) as Record<PairKey, BookLevel[]>;
  const levels = levelsByPair[pair];
  const allLevels = PAIRS.flatMap((p) => levelsByPair[p]);
  const allKeys = [...new Set(allLevels.map((l) => l.key))];
  const houseKeys = levels.filter((l) => !isRef(l)).map((l) => l.key);

  const defaultKey = defaultKeyFor(levels);
  const effectiveKey = selectedKey !== null && levels.some((l) => l.key === selectedKey) ? selectedKey : defaultKey;
  const selectedLevel = levels.find((l) => l.key === effectiveKey) ?? null;

  const heatHouses: { source_id: string; house: string }[] = [];
  for (const l of allLevels) {
    if (!isRef(l) && !heatHouses.some((h) => h.source_id === l.source_id)) heatHouses.push({ source_id: l.source_id, house: l.house });
  }

  const crossBase = selectedLevel !== null && !isRef(selectedLevel) ? selectedLevel : (levels.find((l) => l.key === defaultKey) ?? null);
  const referenceNext = sessions.find((s) => s.reference && stripDemo(s.source_id) === "bcp")?.next_change_at ?? null;

  return {
    levelsByPair,
    levels,
    allLevels,
    allKeys,
    houseKeys,
    effectiveKey,
    selectedLevel,
    heatHouses,
    reference: referenceFor(quotes, sources, pair, now),
    cross: crossFor(levelsByPair, crossBase),
    referenceNext,
  };
}
