/**
 * Client-side mirror of the backend engine, used ONLY in demo mode and for display
 * helpers. The authoritative engine is backend/src/fronteira_fx/engine (Decimal).
 * Formulas:
 *   taxa efetiva  = crédito líquido / débito total
 *   lucro de ciclo = valor final disponível − capital total alocado
 *   ROI           = lucro líquido / capital total alocado
 * Physical routes enter the main ranking only if roi >= best comparable digital roi + 0.01.
 */
import type { Channel, Confidence, Fee, Opportunity, RouteStep } from "./api/types";

export const PHYSICAL_THRESHOLD = 0.01;

export interface StepSpec {
  description: string;
  rate: number; // amount_out per 1 amount_in (before fees)
  rateNote: string;
  feeIn?: Fee[]; // fees charged in the input currency before conversion
  feeOut?: Fee[]; // fees charged in the output currency after conversion
  unknownFee?: string; // label of an essential cost not known -> incomplete
  duration: string;
  promo?: string | null;
  from: RouteStep["from"];
  to: RouteStep["to"];
}

export function runRoute(capital: number, steps: StepSpec[]): { steps: RouteStep[]; final: number; confidence: Confidence; pending: string[] } {
  let amount = capital;
  const out: RouteStep[] = [];
  const pending: string[] = [];
  steps.forEach((s, i) => {
    const feeIn = (s.feeIn ?? []).reduce((a, f) => a + Number(f.amount), 0);
    const afterFeeIn = amount - feeIn;
    const converted = afterFeeIn * s.rate;
    const feeOut = (s.feeOut ?? []).reduce((a, f) => a + Number(f.amount), 0);
    const result = converted - feeOut;
    if (s.unknownFee) pending.push(s.unknownFee);
    out.push({
      n: i + 1,
      description: s.description,
      from: { ...s.from, amount: String(amount) },
      to: { ...s.to, amount: String(result) },
      rate: String(s.rate),
      rate_note: s.rateNote,
      amount_in: String(amount),
      amount_out: String(result),
      fees: [...(s.feeIn ?? []), ...(s.feeOut ?? [])],
      duration: s.duration,
      promo: s.promo ?? null,
      confidence: s.unknownFee ? "incomplete" : "quoted",
      evidence_id: null,
    });
    amount = result;
  });
  return { steps: out, final: amount, confidence: pending.length ? "incomplete" : "quoted", pending };
}

export function effectiveRate(netCredit: number, totalDebit: number): number {
  return totalDebit === 0 ? 0 : netCredit / totalDebit;
}

export function roi(netProfit: number, capital: number): number {
  return capital === 0 ? 0 : netProfit / capital;
}

/** Apply ranking rules; returns a new array sorted by roi desc with in_main_ranking set. */
export function rankOpportunities(list: Opportunity[]): Opportunity[] {
  const byKey = new Map<string, number>(); // best digital roi per (capital, kind)
  for (const o of list) {
    if (o.channel === "digital") {
      const k = `${o.capital_brl}:${o.kind}`;
      byKey.set(k, Math.max(byKey.get(k) ?? -Infinity, Number(o.roi)));
    }
  }
  return list
    .map((o) => {
      const r = Number(o.roi);
      const gain = Number(o.net_gain_brl);
      const bestDigital = byKey.get(`${o.capital_brl}:${o.kind}`);
      let inMain = false;
      let reason = "";
      if (o.channel === "digital") {
        inMain = gain > 0;
        reason = inMain ? "digital com ganho líquido positivo" : "digital sem ganho líquido";
      } else {
        const threshold = (bestDigital ?? -Infinity) + PHYSICAL_THRESHOLD;
        // Physical needs a positive net gain AND >= best comparable digital + 1 p.p.
        inMain = gain > 0 && (bestDigital === undefined || r >= threshold);
        reason = !(gain > 0)
          ? "físico sem ganho líquido após custos"
          : inMain
            ? `físico supera melhor digital em ≥ 1 p.p. (ROI ${(r * 100).toFixed(3)} % vs ${((bestDigital ?? 0) * 100).toFixed(3)} %)`
            : `físico abaixo do limite: precisa ROI ≥ ${(threshold * 100).toFixed(3)} %`;
      }
      return { ...o, in_main_ranking: inMain, ranking_reason: reason, comparable_best_digital_roi: bestDigital !== undefined ? String(bestDigital) : null };
    })
    .sort((a, b) => Number(b.roi) - Number(a.roi));
}

export function channelLabel(c: Channel): string {
  return c === "digital" ? "Digital" : "Presencial";
}
