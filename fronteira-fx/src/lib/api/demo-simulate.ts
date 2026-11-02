import type { SimulationRequest, SimulationResponse } from "./types";
import { DEMO_CAPITALS, demoOpportunities } from "./demo-data";

/** Demo-only adaptive search: tests the standard amounts plus the requested capital. */
export async function simulateDemo(req: SimulationRequest): Promise<SimulationResponse> {
  const capital = Number(req.capital_brl);
  const nearest = DEMO_CAPITALS.reduce((a, b) => (Math.abs(b - capital) < Math.abs(a - capital) ? b : a));
  const kindFilter = req.objective === "cycle" ? "cycle" : req.objective === "remittance" ? "remittance_saving" : "purchase_saving";
  const opportunities = demoOpportunities
    .filter((o) => o.capital_brl === String(nearest) && req.channels.includes(o.channel) && (o.kind === kindFilter || req.objective === "cycle"))
    .map((o) => ({ ...o, valuation_currency: req.valuation_currency }));
  return {
    opportunities,
    search: {
      amounts_tested: [...DEMO_CAPITALS.map(String), String(capital)],
      boundaries: [{ low: "10000", high: "25000", low_winner: "demo-chaco", high_winner: "demo-alberdi", low_roi_sign: "+", high_roi_sign: "+", reason: "Alberdi PJC passa a vencer acima de R$ 25 mil (demonstração)", refined: false }],
    },
    simulation_id: null, // demo never persists
  };
}
