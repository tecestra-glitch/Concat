/**
 * DEMONSTRAÇÃO — dados ilustrativos, centrados na referência BCP de 2026-10-30 (USD/PYG 5.944,76; USD/BRL 5,4043).
 * Nunca misturar com dados reais.
 * Every record carries data_mode = "demo". Values are plausible but invented, and
 * the generator is deterministic (seeded) so screenshots/tests are reproducible.
 */
import type { Account, Branch, Evidence, HistoryPoint, HistorySeries, JournalEntry, Opportunity, Quote, Source } from "./types";
import { rankOpportunities, runRoute } from "../finance";

// Anchored to the current 5-minute bucket at module load so ages look realistic; the generator itself is seeded.
const DEMO_NOW = Math.floor(Date.now() / 300_000) * 300_000;

/**
 * Historical Western Union fixture (R$ 5.000, Brasil → Paraguai, Pix, 100 % desconto na tarifa, sem banco).
 * Used by backend tests only. NEVER presented as current; the demo quotes below are illustrative.
 */
export const WU_HISTORICAL_FIXTURE = {
  amount_brl: 5000,
  bank_account: { receive_pyg: 5_401_871, duration: "0–4 dias úteis" },
  cash_pickup: { receive_pyg: 5_328_209, duration: "minutos" },
  promo: "100 % desconto na tarifa",
  note: "histórico — não é cotação atual",
} as const;

function seeded(seed: number) {
  let s = seed >>> 0;
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0;
    return s / 2 ** 32;
  };
}

export const demoSources: Source[] = [
  { id: "chaco", name: "Cambios Chaco", kind: "exchange_house", method: "html", url: "https://www.cambioschaco.com.py/", health: "ok", last_success_at: iso(-120), last_error: null, capabilities: ["branch_table", "buy_sell", "usd_pyg", "brl_pyg"], limitations: ["sem API oficial", "cotação por filial"], coverage: { cities: ["CDE", "ASU"], currencies: ["USD", "BRL", "PYG"] }, poll_interval_s: 300, data_mode: "demo" },
  { id: "alberdi", name: "Cambios Alberdi", kind: "exchange_house", method: "html", url: "https://www.cambiosalberdi.com/", health: "ok", last_success_at: iso(-200), last_error: null, capabilities: ["branch_table", "buy_sell"], limitations: ["sem API oficial"], coverage: { cities: ["CDE", "ASU", "PJC"], currencies: ["USD", "BRL", "PYG"] }, poll_interval_s: 300, data_mode: "demo" },
  { id: "norte", name: "Cambios Norte", kind: "exchange_house", method: "html", url: "https://www.nortecambios.com.py/", health: "degraded", last_success_at: iso(-3600), last_error: "cadeia TLS inválida (verificação falhou)", capabilities: ["buy_sell"], limitations: ["certificado TLS com cadeia incompleta"], coverage: { cities: ["ASU", "PJC"], currencies: ["USD", "BRL", "PYG"] }, poll_interval_s: 300, data_mode: "demo" },
  { id: "bonanza", name: "Bonanza Cambios", kind: "exchange_house", method: "browser", url: "https://www.bonanzacambios.com.py/", health: "ok", last_success_at: iso(-300), last_error: null, capabilities: ["buy_sell"], limitations: ["página renderizada por JavaScript"], coverage: { cities: ["ASU", "CDE"], currencies: ["USD", "BRL", "PYG"] }, poll_interval_s: 300, data_mode: "demo" },
  { id: "bcp", name: "BCP (referência)", kind: "central_bank", method: "html", url: "https://www.bcp.gov.py/webapps/web/cotizacion/monedas", health: "ok", last_success_at: iso(-900), last_error: null, capabilities: ["market_reference"], limitations: ["referência diária, não executável"], coverage: { cities: [], currencies: ["USD", "BRL", "PYG"] }, poll_interval_s: 3600, data_mode: "demo" },
  { id: "ueno", name: "ueno", kind: "bank", method: "html", url: "https://www.ueno.com.py/cambio-de-moneda/", health: "ok", last_success_at: iso(-180), last_error: null, capabilities: ["buy_sell", "account", "card"], limitations: ["câmbio efetivo em app pode diferir"], coverage: { cities: [], currencies: ["USD", "BRL", "PYG"] }, poll_interval_s: 300, data_mode: "demo" },
  { id: "westernunion", name: "Western Union", kind: "remittance", method: "browser", url: "https://www.westernunion.com/br/pt/web/send-money/start", health: "degraded", last_success_at: iso(-5400), last_error: "simulador exigiu nova sessão", capabilities: ["simulator_by_amount", "receive_methods", "promo"], limitations: ["contexto completo obrigatório", "depende de navegador"], coverage: { cities: [], currencies: ["BRL", "PYG"] }, poll_interval_s: 900, data_mode: "demo" },
  { id: "nomad", name: "Nomad", kind: "fintech", method: "html", url: "https://www.nomadglobal.com/cotacao/dolar-hoje", health: "ok", last_success_at: iso(-240), last_error: null, capabilities: ["public_calculator"], limitations: ["proposta efetiva depende da conta"], coverage: { cities: [], currencies: ["BRL", "USD"] }, poll_interval_s: 300, data_mode: "demo" },
  { id: "revolut", name: "Revolut", kind: "fintech", method: "manual", url: "https://www.revolut.com/currency-converter/", health: "blocked", last_success_at: null, last_error: "HTTP 403 — conversor público bloqueado para automação", capabilities: [], limitations: ["região e disponibilidade registradas manualmente"], coverage: { cities: [], currencies: ["BRL", "USD"] }, poll_interval_s: 900, data_mode: "demo" },
];

function iso(offsetSeconds: number): string {
  return new Date(DEMO_NOW + offsetSeconds * 1000).toISOString();
}

/** FNV-1a 32 bits — deterministic, dependency-free. Only for demo keys/fixtures. */
function hash(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619);
  return h >>> 0;
}

/** Canonical JSON of a quote context: keys sorted, so the same context always hashes alike. */
function canonicalContext(ctx: Record<string, string | null>): string {
  const sorted: Record<string, string | null> = {};
  for (const k of Object.keys(ctx).sort()) sorted[k] = ctx[k];
  return JSON.stringify(sorted);
}

/**
 * D2 series key, same shape the backend emits:
 * `{source}:{city|digital}:{base}/{quote}:{modality}[:@{branch}][:{amount}][:{ctx8}]`.
 * The optional segments appear only when present. `ctx8` is 8 hex chars of a hash of the
 * canonical context (the backend uses sha256; the demo uses FNV-1a — the format is identical).
 */
export function seriesKey(q: Omit<Quote, "series_key">): string {
  let key = `${q.source_id}:${q.city ?? "digital"}:${q.base}/${q.quote}:${q.modality}`;
  if (q.branch_id) key += `:@${q.branch_id}`;
  if (q.amount_base) key += `:${q.amount_base}`;
  if (q.context && Object.keys(q.context).length > 0) key += `:${hash(canonicalContext(q.context)).toString(16).padStart(8, "0")}`;
  return key;
}

function withSeriesKey(q: Omit<Quote, "series_key">): Quote {
  return { ...q, series_key: seriesKey(q) };
}

interface QSpec {
  source: string; branch: string | null; city: Quote["city"]; base: Quote["base"]; quote: Quote["quote"];
  buy: number | null; sell: number | null; modality: Quote["modality"]; kind: Quote["kind"]; channel: Quote["channel"]; age: number; declaredAge?: number | null;
}

const specs: QSpec[] = [
  // USD/PYG — casas (PYG por 1 USD)
  { source: "chaco", branch: "chaco-cde-centro", city: "CDE", base: "USD", quote: "PYG", buy: 5905, sell: 5975, modality: "cash", kind: "indicative", channel: "physical", age: 120 },
  { source: "chaco", branch: "chaco-asu-shopping", city: "ASU", base: "USD", quote: "PYG", buy: 5900, sell: 5980, modality: "cash", kind: "indicative", channel: "physical", age: 120 },
  { source: "alberdi", branch: "alberdi-cde", city: "CDE", base: "USD", quote: "PYG", buy: 5915, sell: 5965, modality: "cash", kind: "indicative", channel: "physical", age: 200 },
  { source: "alberdi", branch: "alberdi-pjc", city: "PJC", base: "USD", quote: "PYG", buy: 5890, sell: 5995, modality: "cash", kind: "indicative", channel: "physical", age: 200 },
  { source: "norte", branch: "norte-asu", city: "ASU", base: "USD", quote: "PYG", buy: 5902, sell: 5978, modality: "cash", kind: "indicative", channel: "physical", age: 3600, declaredAge: 3600 },
  { source: "bonanza", branch: "bonanza-asu", city: "ASU", base: "USD", quote: "PYG", buy: 5910, sell: 5970, modality: "cash", kind: "indicative", channel: "physical", age: 300 },
  // BRL/PYG — casas (PYG por 1 BRL)
  { source: "chaco", branch: "chaco-cde-centro", city: "CDE", base: "BRL", quote: "PYG", buy: 1092, sell: 1112, modality: "cash", kind: "indicative", channel: "physical", age: 120 },
  { source: "alberdi", branch: "alberdi-cde", city: "CDE", base: "BRL", quote: "PYG", buy: 1095, sell: 1110, modality: "cash", kind: "indicative", channel: "physical", age: 200 },
  { source: "alberdi", branch: "alberdi-pjc", city: "PJC", base: "BRL", quote: "PYG", buy: 1086, sell: 1118, modality: "cash", kind: "indicative", channel: "physical", age: 200 },
  { source: "bonanza", branch: "bonanza-asu", city: "ASU", base: "BRL", quote: "PYG", buy: 1090, sell: 1114, modality: "cash", kind: "indicative", channel: "physical", age: 300 },
  // BCP reference
  { source: "bcp", branch: null, city: null, base: "USD", quote: "PYG", buy: 5944.76, sell: 5944.76, modality: "transfer", kind: "market_reference", channel: "digital", age: 900, declaredAge: 43200 },
  { source: "bcp", branch: null, city: null, base: "BRL", quote: "PYG", buy: 1099.99, sell: 1099.99, modality: "transfer", kind: "market_reference", channel: "digital", age: 900, declaredAge: 43200 },
  // ueno digital
  { source: "ueno", branch: null, city: null, base: "USD", quote: "PYG", buy: 5880, sell: 5940, modality: "account", kind: "indicative", channel: "digital", age: 180 },
  { source: "ueno", branch: null, city: null, base: "BRL", quote: "PYG", buy: 1078, sell: 1128, modality: "account", kind: "indicative", channel: "digital", age: 180 },
  // Nomad BRL->USD (USD por 1 BRL => inverse of R$ per US$)
  { source: "nomad", branch: null, city: null, base: "USD", quote: "BRL", buy: null, sell: 5.4310, modality: "account", kind: "indicative", channel: "digital", age: 240 },
];

export const demoQuotes: Quote[] = specs.map((s, i) => withSeriesKey({
  id: `demo-q-${i}`,
  source_id: s.source,
  branch_id: s.branch,
  city: s.city,
  base: s.base,
  quote: s.quote,
  buy: s.buy === null ? null : String(s.buy),
  sell: s.sell === null ? null : String(s.sell),
  unit_note: `${s.quote} por 1 ${s.base}`,
  amount_base: null,
  modality: s.modality,
  kind: s.kind,
  channel: s.channel,
  context: null,
  fees: [],
  captured_at: iso(-s.age),
  declared_updated_at: s.declaredAge ? iso(-s.declaredAge) : null,
  valid_until: null,
  evidence_id: `demo-ev-${i}`,
  data_mode: "demo",
}));

/** GET /v1/sources/{id}/branches — one entry per distinct branch in the demo specs. */
const BRANCH_NAME: Record<string, string> = {
  "chaco-cde-centro": "Chaco — CDE Centro",
  "chaco-asu-shopping": "Chaco — ASU Shopping",
  "alberdi-cde": "Alberdi — Ciudad del Este",
  "alberdi-pjc": "Alberdi — Pedro Juan Caballero",
  "norte-asu": "Norte — Asunción",
  "bonanza-asu": "Bonanza — Asunción",
};

export const demoBranches: Branch[] = specs.reduce<Branch[]>((acc, s) => {
  if (!s.branch || s.city === null || acc.some((b) => b.id === s.branch)) return acc;
  acc.push({ id: s.branch, source_id: s.source, name: BRANCH_NAME[s.branch] ?? s.branch, city: s.city, address: null });
  return acc;
}, []);

/** Western Union simulator quotes carry full context; the two receive methods are distinct quotes. */
export const demoWesternUnionQuotes: Quote[] = [
  // illustrative: rate improves slightly with the amount; cash pickup pays less than bank account
  { receive: "bank_account", amount: 5000, out: 5_505_000, dur: "0–4 dias úteis" },
  { receive: "cash_pickup", amount: 5000, out: 5_430_000, dur: "minutos" },
  { receive: "bank_account", amount: 10000, out: 11_020_000, dur: "0–4 dias úteis" },
  { receive: "bank_account", amount: 25000, out: 27_575_000, dur: "0–4 dias úteis" },
  { receive: "bank_account", amount: 50000, out: 55_200_000, dur: "0–4 dias úteis" },
].map((w, i) => withSeriesKey({
  id: `demo-wu-${i}`,
  source_id: "westernunion",
  branch_id: null,
  city: null,
  base: "BRL" as const,
  quote: "PYG" as const,
  buy: null,
  sell: String(w.out / w.amount),
  unit_note: "PYG por 1 BRL (simulador, valor específico)",
  amount_base: String(w.amount),
  modality: w.receive === "cash_pickup" ? ("cash" as const) : ("account" as const),
  kind: "indicative" as const,
  channel: "digital" as const,
  context: { origin: "BR", destination: "PY", payment: "pix", receive: w.receive, bank: null, channel: "web", promo: "fee_100_off", duration: w.dur },
  fees: [{ label: "tarifa (100 % desconto)", amount: "0", currency: "BRL" as const }],
  captured_at: iso(-5400),
  declared_updated_at: null,
  valid_until: null,
  evidence_id: `demo-ev-wu-${i}`,
  data_mode: "demo" as const,
}));

export const allDemoQuotes: Quote[] = [...demoQuotes, ...demoWesternUnionQuotes];

/**
 * GET /v1/history?key= (demo): the series is addressed by `series_key` and echoes it.
 * An unknown key answers an empty series (like the backend), never another series' points.
 */
export function demoHistory(key: string, points = 288, stepMs = 5 * 60 * 1000): HistorySeries {
  const q = allDemoQuotes.find((x) => x.series_key === key);
  if (!q) return { key, points: [] };
  const rnd = seeded(hash(key));
  const baseBuy = Number(q.buy ?? q.sell ?? 1);
  const baseSell = Number(q.sell ?? q.buy ?? 1);
  const out: HistoryPoint[] = [];
  let drift = 0;
  for (let i = points - 1; i >= 0; i--) {
    drift += (rnd() - 0.5) * 0.0008;
    drift *= 0.98;
    const f = 1 + drift + Math.sin(i / 37) * 0.0012;
    const t = new Date(DEMO_NOW - i * stepMs).toISOString();
    const buy = baseBuy * f;
    const sell = baseSell * f;
    // simulate a gap (collector down) between slots 40–46
    if (i > 40 && i < 46) continue;
    out.push({ t, buy: buy.toFixed(4), sell: sell.toFixed(4), mid: ((buy + sell) / 2).toFixed(4) });
  }
  return { key, points: out };
}

export const demoAccounts: Account[] = [
  { id: "acc-ueno-pyg", institution: "ueno", label: "ueno conta PYG", currency: "PYG", kind: "bank", location: "digital", balance_free: "1250000", balance_reserved: "0", balance_in_transit: "0", updated_at: iso(-600) },
  { id: "acc-ueno-usd", institution: "ueno", label: "ueno conta USD", currency: "USD", kind: "bank", location: "digital", balance_free: "320", balance_reserved: "0", balance_in_transit: "0", updated_at: iso(-600) },
  { id: "acc-ueno-card", institution: "ueno", label: "ueno cartão de crédito", currency: "PYG", kind: "card_credit", location: "digital", balance_free: "0", balance_reserved: "480000", balance_in_transit: "0", updated_at: iso(-600) },
  { id: "acc-nomad-usd", institution: "Nomad", label: "Nomad conta USD", currency: "USD", kind: "fintech", location: "digital", balance_free: "1500", balance_reserved: "0", balance_in_transit: "0", updated_at: iso(-3600) },
  { id: "acc-revolut-usd", institution: "Revolut", label: "Revolut USD", currency: "USD", kind: "fintech", location: "digital", balance_free: "0", balance_reserved: "0", balance_in_transit: "0", updated_at: iso(-86400) },
  { id: "acc-brl-bank", institution: "Banco BR", label: "Conta BRL (Pix)", currency: "BRL", kind: "bank", location: "digital", balance_free: "25000", balance_reserved: "0", balance_in_transit: "5000", updated_at: iso(-60) },
  { id: "acc-cash-cde", institution: "Dinheiro", label: "Espécie em CDE", currency: "USD", kind: "cash", location: "CDE", balance_free: "0", balance_reserved: "0", balance_in_transit: "0", updated_at: iso(-86400) },
];

function buildOpportunities(capital: number): Opportunity[] {
  const wu = demoWesternUnionQuotes.find((q) => q.amount_base === String(capital) && q.context?.receive === "bank_account");
  const wuRate = wu ? Number(wu.sell) : 1080;
  const chacoBrlBuy = Number(demoQuotes.find((q) => q.source_id === "chaco" && q.base === "BRL" && q.city === "CDE")!.buy);
  const chacoBrlSell = Number(demoQuotes.find((q) => q.source_id === "chaco" && q.base === "BRL" && q.city === "CDE")!.sell);
  const uenoUsdSell = Number(demoQuotes.find((q) => q.source_id === "ueno" && q.base === "USD")!.sell);
  const chacoUsdBuy = Number(demoQuotes.find((q) => q.source_id === "chaco" && q.base === "USD" && q.city === "CDE")!.buy);
  const nomadSell = Number(demoQuotes.find((q) => q.source_id === "nomad")!.sell);

  const list: Opportunity[] = [];

  // 1. Remittance saving (digital): Pix -> WU -> ueno PYG vs reference BCP BRL/PYG
  {
    const r = runRoute(capital, [
      { description: "Pix BRL → Western Union → conta ueno (PYG)", rate: wuRate, rateNote: "PYG por 1 BRL (simulador WU)", duration: "0–4 dias úteis", promo: "100 % desconto na tarifa", feeIn: [{ label: "tarifa WU", amount: "0", currency: "BRL" }], from: pos("BRL", "acc-brl-bank", "digital", "transfer"), to: pos("PYG", "acc-ueno-pyg", "digital", "account") },
    ]);
    const refPyg = capital * 1099.99; // BCP reference (2026-10-30: USD/PYG 5944.76, USD/BRL 5.4043)
    const gainPyg = r.final - refPyg;
    const gainBrl = gainPyg / 1099.99;
    list.push(opp("demo-op-wu", "Remessa Pix → WU → ueno vs referência BCP", "remittance_saving", "digital", null, capital, capital + gainBrl, gainBrl, wuRate, r.steps, r.confidence, r.pending));
  }
  // 2. Digital cycle: BRL -> ueno PYG (WU) -> ueno USD -> Nomad? (sell USD for BRL at Nomad rate) micro gain
  {
    const r = runRoute(capital, [
      { description: "Pix BRL → WU → conta ueno PYG", rate: wuRate, rateNote: "PYG por 1 BRL", duration: "0–4 dias úteis", promo: "100 % desconto na tarifa", from: pos("BRL", "acc-brl-bank", "digital", "transfer"), to: pos("PYG", "acc-ueno-pyg", "digital", "account") },
      { description: "ueno: PYG → USD (venda USD do banco)", rate: 1 / uenoUsdSell, rateNote: "USD por 1 PYG", duration: "imediato", from: pos("PYG", "acc-ueno-pyg", "digital", "account"), to: pos("USD", "acc-ueno-usd", "digital", "account") },
      { description: "USD → BRL via conta Nomad (cotação pública)", rate: nomadSell * 0.9961, rateNote: "BRL por 1 USD (líquido de spread)", duration: "1 dia útil", unknownFee: "IOF/custo de transferência USD→Nomad não confirmado", from: pos("USD", "acc-nomad-usd", "digital", "account"), to: pos("BRL", "acc-brl-bank", "digital", "transfer") },
    ]);
    list.push(opp("demo-op-cycle-digital", "Ciclo digital BRL → ueno → USD → Nomad → BRL", "cycle", "digital", null, capital, r.final, r.final - capital, r.final / capital, r.steps, r.confidence, r.pending));
  }
  // 3. Physical cycle in CDE: BRL cash -> USD cash (Chaco) -> BRL cash (Chaco)
  {
    const r = runRoute(capital, [
      { description: "Chaco CDE: BRL espécie → PYG", rate: chacoBrlBuy, rateNote: "PYG por 1 BRL (compra da casa)", duration: "presencial", from: pos("BRL", null, "CDE", "cash"), to: pos("PYG", null, "CDE", "cash") },
      { description: "Chaco CDE: PYG → USD", rate: 1 / 5975, rateNote: "USD por 1 PYG (venda USD)", duration: "presencial", from: pos("PYG", null, "CDE", "cash"), to: pos("USD", null, "CDE", "cash") },
      { description: "Chaco CDE: USD → BRL", rate: chacoUsdBuy / chacoBrlSell, rateNote: "BRL por 1 USD (cruzado)", duration: "presencial", feeOut: [{ label: "deslocamento", amount: "60", currency: "BRL" }], from: pos("USD", null, "CDE", "cash"), to: pos("BRL", null, "CDE", "cash") },
    ]);
    list.push(opp("demo-op-cycle-cde", "Ciclo presencial CDE (Chaco) BRL → PYG → USD → BRL", "cycle", "physical", "CDE", capital, r.final, r.final - capital, r.final / capital, r.steps, r.confidence, r.pending));
  }
  // 4. Physical remittance alternative: carry BRL cash to Alberdi PJC and deposit at ueno
  {
    const r = runRoute(capital, [
      { description: "Alberdi PJC: BRL espécie → PYG espécie", rate: 1086 + (capital >= 25000 ? 30 : 0), rateNote: "PYG por 1 BRL (compra da casa; melhora acima de R$ 25 mil)", duration: "presencial", feeIn: [{ label: "deslocamento + estadia", amount: "180", currency: "BRL" }], from: pos("BRL", null, "PJC", "cash"), to: pos("PYG", null, "PJC", "cash") },
      { description: "Depósito em conta ueno", rate: 1, rateNote: "sem conversão", duration: "imediato", from: pos("PYG", null, "PJC", "cash"), to: pos("PYG", "acc-ueno-pyg", "digital", "account") },
    ]);
    const refPyg = capital * 1099.99;
    const gainBrl = (r.final - refPyg) / 1099.99;
    list.push(opp("demo-op-pjc", "Remessa presencial PJC (Alberdi) → depósito ueno", "remittance_saving", "physical", "PJC", capital, capital + gainBrl, gainBrl, r.final / capital, r.steps, r.confidence, r.pending));
  }
  // 5. Purchase saving: pay a 2,000,000 PYG purchase via ueno card funded by WU vs paying with BR card (IOF+spread ~ 6%)
  {
    const purchasePyg = 2_000_000;
    const costViaWu = purchasePyg / wuRate;
    const costBrCard = (purchasePyg / 1099.99) * 1.0638;
    const saving = costBrCard - costViaWu;
    const r = runRoute(costViaWu, [
      { description: "Pix BRL → WU → saldo ueno PYG", rate: wuRate, rateNote: "PYG por 1 BRL", duration: "0–4 dias úteis", promo: "100 % desconto na tarifa", from: pos("BRL", "acc-brl-bank", "digital", "transfer"), to: pos("PYG", "acc-ueno-pyg", "digital", "account") },
      { description: "Compra ₲ 2.000.000 no cartão de débito ueno (moeda da compra: PYG)", rate: 1, rateNote: "sem conversão (saldo PYG debitado)", duration: "imediato", unknownFee: "moeda debitada e encargos do cartão ainda não validados", from: pos("PYG", "acc-ueno-pyg", "digital", "account"), to: pos("PYG", "acc-ueno-card", "digital", "card_debit") },
    ]);
    list.push(opp("demo-op-card", "Pagar compra ₲ 2 mi: WU → ueno débito vs cartão BR", "purchase_saving", "digital", null, capital, capital + saving, saving, wuRate, r.steps, "incomplete", [...r.pending, "spread do cartão BR estimado (6,38 %)"]));
  }
  return rankOpportunities(list);
}

function pos(currency: Opportunity["valuation_currency"], account: string | null, location: string, modality: Opportunity["steps"][number]["from"]["modality"]) {
  return { currency, account_id: account, location, modality, amount: "0" };
}

function opp(id: string, title: string, kind: Opportunity["kind"], channel: Opportunity["channel"], city: Opportunity["city"], capital: number, finalValue: number, gain: number, effRate: number, steps: Opportunity["steps"], confidence: Opportunity["confidence"], pending: string[]): Opportunity {
  return {
    id: `${id}-${capital}`,
    title,
    kind,
    channel,
    city,
    capital_brl: String(capital),
    final_value_brl: finalValue.toFixed(4),
    net_gain_brl: gain.toFixed(4),
    roi: (gain / capital).toFixed(8),
    effective_rate: effRate.toFixed(6),
    valuation_currency: "BRL",
    steps,
    confidence,
    pending_costs: pending,
    in_main_ranking: false,
    ranking_reason: "",
    comparable_best_digital_roi: null,
    computed_at: iso(-60),
    data_mode: "demo",
  };
}

export const DEMO_CAPITALS = [5000, 10000, 25000, 50000];
export const demoOpportunities: Opportunity[] = DEMO_CAPITALS.flatMap(buildOpportunities);

export const demoEvidence: Evidence[] = allDemoQuotes.map((q) => ({
  id: q.evidence_id ?? q.id,
  source_id: q.source_id,
  kind: q.source_id === "westernunion" ? "screenshot" : "html",
  url: demoSources.find((s) => s.id === q.source_id)?.url ?? "",
  captured_at: q.captured_at,
  sha256: hash(q.id).toString(16).padStart(8, "0").repeat(8),
  excerpt: `[DEMO] ${q.source_id} ${q.base}/${q.quote} compra ${q.buy ?? "—"} venda ${q.sell ?? "—"} (${q.unit_note})`,
  rules: [`parser ${q.source_id} v1 (demo)`],
}));

export const demoJournal: JournalEntry[] = [
  { id: "j1", ts: iso(-86400 * 2), kind: "note", text: "Início do monitoramento em modo demonstração.", amounts: [], account_ids: [] },
  { id: "j2", ts: iso(-86400), kind: "operation", text: "Simulação registrada: Pix R$ 5.000 → WU → ueno (não executada).", amounts: [{ label: "capital", amount: "5000", currency: "BRL" }], account_ids: ["acc-brl-bank", "acc-ueno-pyg"] },
  { id: "j3", ts: iso(-3600), kind: "reconciliation", text: "Saldos ueno informados manualmente conferidos com o app.", amounts: [], account_ids: ["acc-ueno-pyg", "acc-ueno-usd"] },
];

export const DEMO_SERVER_TIME = new Date(DEMO_NOW).toISOString();
