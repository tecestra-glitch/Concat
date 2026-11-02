import type { Currency, HistoryPoint } from "@/lib/api/types";
import { toNumber } from "@/lib/format";
import { formatRateFixed } from "@/components/ui/rate";

/** Rótulo acessível do gráfico: par, faixa de compra e janela coberta pelos pontos. */
export function chartAriaLabel(points: HistoryPoint[], quote: Currency, pair: string): string {
  const times = points.map((p) => Date.parse(p.t)).filter((t) => Number.isFinite(t));
  if (times.length === 0) return `${pair}, sem dados no período`;
  const buys = points.map((p) => toNumber(p.buy)).filter((v): v is number => v !== null);
  const spanMin = Math.round((Math.max(...times) - Math.min(...times)) / 60_000);
  const window = spanMin >= 60 ? `últimas ${Math.round(spanMin / 60)} h` : `últimos ${spanMin} min`;
  if (buys.length === 0) return `${pair}, sem preço de compra, ${window}`;
  return `${pair}, compra de ${formatRateFixed(Math.min(...buys), quote)} a ${formatRateFixed(Math.max(...buys), quote)}, ${window}`;
}
