/**
 * Derivações da tela de pregão que não dependem das consultas de resumo (§24.4): níveis por par,
 * série escolhida, chaves para o resumo e as miniaturas, casas do mapa de calor, linha de
 * referência do gráfico e pernas do cruzamento. Puro: o container (`pregao.tsx`) só liga os hooks.
 * Referências (BCP, dolarPy) nunca são série padrão nem perna de cruzamento.
 */
import type { Quote, Source } from "@/lib/api/types";
import { legOf, type Leg } from "./cross";
import { midOf } from "./candles";
import { defaultKeyFor, houseName, refQuoteFor, toBookLevels } from "./derive";
import { PAIRS, type BookLevel, type HouseSession, type PairKey } from "./types";

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
/** Contexto da série: a chave sem o par (`fonte:cidade:modalidade[:@filial][:montante][:ctx]`). */
const contextOf = (key: string) => key.split(":").filter((_, i) => i !== 2).join(":");

/** Próximo par na sequência de `PAIRS`, dando a volta nos dois sentidos. */
export function cyclePair(pair: PairKey, dir: 1 | -1): PairKey {
  const i = PAIRS.indexOf(pair);
  return PAIRS[(i + dir + PAIRS.length) % PAIRS.length];
}

/** Linha de referência do gráfico: valor e rótulo vêm da mesma cotação (`refQuoteFor`, a do ágio). */
function referenceFor(quotes: Quote[], sources: Source[], pair: PairKey, now: Date): PregaoReference | null {
  const ref = refQuoteFor(quotes, pair, now);
  const mid = ref === null ? null : midOf(ref.buy, ref.sell);
  if (ref === null || mid === null) return null;
  return { value: String(mid), label: `≈ ${houseName(sources, ref.source_id)}` };
}

/** Pernas do cruzamento no mesmo contexto da casa base: casa, cidade, modalidade, filial, montante e contexto. */
function crossFor(levelsByPair: Record<PairKey, BookLevel[]>, base: BookLevel | null): PregaoCross {
  if (base === null) return { house: "—", usdPyg: null, usdBrl: null, direct: null };
  const ctx = contextOf(base.key);
  const same = (l: BookLevel) => !isRef(l) && contextOf(l.key) === ctx;
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
