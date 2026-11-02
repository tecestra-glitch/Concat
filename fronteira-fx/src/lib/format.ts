/**
 * pt-BR number formatting. Micro-gains must never be visually rounded to zero:
 * `formatMoney` widens the fraction digits until the value is distinguishable from 0.
 */
const LOCALE = "pt-BR";

export function toNumber(v: string | number | null | undefined): number | null {
  if (v === null || v === undefined || v === "") return null;
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : null;
}

const CURRENCY_DIGITS: Record<string, number> = { BRL: 2, USD: 2, PYG: 0 };
const CURRENCY_SYMBOL: Record<string, string> = { BRL: "R$", USD: "US$", PYG: "₲" };

/** Smallest number of fraction digits (>= min) at which |v| does not render as 0. */
export function significantFractionDigits(v: number, min: number, max = 8): number {
  if (v === 0) return min;
  // Keep at least two significant digits visible for small magnitudes.
  let d = min;
  while (d < max && Math.abs(v) * Math.pow(10, d) < 10) d++;
  return d;
}

export function formatMoney(
  value: string | number | null | undefined,
  currency: "BRL" | "USD" | "PYG",
  opts: { sign?: boolean; compact?: boolean } = {},
): string {
  const n = toNumber(value);
  if (n === null) return "—";
  const min = CURRENCY_DIGITS[currency] ?? 2;
  const digits = significantFractionDigits(n, min);
  const body = new Intl.NumberFormat(LOCALE, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
    notation: opts.compact ? "compact" : "standard",
  }).format(Math.abs(n));
  const sign = n < 0 ? "−" : opts.sign && n > 0 ? "+" : "";
  return `${sign}${CURRENCY_SYMBOL[currency]} ${body}`;
}

/** Exchange rate: PYG rates have no decimals beyond the quoted precision; BRL/USD rates show 4. */
export function formatRate(value: string | number | null | undefined, quote: "BRL" | "USD" | "PYG"): string {
  const n = toNumber(value);
  if (n === null) return "—";
  const digits = quote === "PYG" ? (Number.isInteger(n) ? 0 : 2) : 4;
  return new Intl.NumberFormat(LOCALE, { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(n);
}

/** Percent from a ratio (0.0084 -> "0,84 %"); widens digits so micro values stay visible. */
export function formatPercent(ratio: string | number | null | undefined, opts: { sign?: boolean } = {}): string {
  const n = toNumber(ratio);
  if (n === null) return "—";
  const pct = n * 100;
  const digits = significantFractionDigits(pct, 2, 6);
  const body = new Intl.NumberFormat(LOCALE, { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(Math.abs(pct));
  const sign = pct < 0 ? "−" : opts.sign && pct > 0 ? "+" : "";
  return `${sign}${body} %`;
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return new Intl.DateTimeFormat(LOCALE, { dateStyle: "short", timeStyle: "short" }).format(d);
}

export function formatAge(iso: string | null | undefined, now: number = Date.now()): string {
  if (!iso) return "sem dados";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "sem dados";
  const s = Math.max(0, Math.round((now - t) / 1000));
  if (s < 60) return `há ${s} s`;
  const m = Math.round(s / 60);
  if (m < 60) return `há ${m} min`;
  const h = Math.round(m / 60);
  if (h < 48) return `há ${h} h`;
  return `há ${Math.round(h / 24)} d`;
}

export function ageSeconds(iso: string | null | undefined, now: number = Date.now()): number | null {
  if (!iso) return null;
  const t = new Date(iso).getTime();
  return Number.isNaN(t) ? null : Math.max(0, (now - t) / 1000);
}
