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

/** Boundary of the adaptive search: «R$ 10.000–R$ 25.000: motivo» (capital range in BRL). */
export function formatBoundary(b: { low: string; high: string; reason: string }): string {
  return `${formatMoney(b.low, "BRL")}–${formatMoney(b.high, "BRL")}: ${b.reason}`;
}

/** «label: R$ 9,90», «label: 1,50 %», «label: R$ 9,90 + 1,50 %» or «label: —» when nothing is known. */
export function formatFee(f: { label: string; amount: string | null; currency: "BRL" | "USD" | "PYG"; pct?: string | null }): string {
  const parts: string[] = [];
  if (toNumber(f.amount) !== null) parts.push(formatMoney(f.amount, f.currency));
  if (toNumber(f.pct) !== null) parts.push(formatPercent(f.pct));
  return `${f.label}: ${parts.length ? parts.join(" + ") : "—"}`;
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return new Intl.DateTimeFormat(LOCALE, { dateStyle: "short", timeStyle: "short" }).format(d);
}

/**
 * Relative age against an explicit clock (`now` in ms). The clock is mandatory so that
 * components take it from `useNow()` and never read `Date.now()` during render.
 */
export function formatAge(iso: string | null | undefined, now: number): string {
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

export function ageSeconds(iso: string | null | undefined, now: number): number | null {
  if (!iso) return null;
  const t = new Date(iso).getTime();
  return Number.isNaN(t) ? null : Math.max(0, (now - t) / 1000);
}

const THOUSANDS_GROUPS = /^\d{1,3}(\.\d{3})+$/;
const PLAIN_DIGITS = /^\d+$/;

/**
 * Reads a number typed in pt-BR ("5.000", "5.000,50", "0,25") or with a plain dot
 * decimal ("0.25", "5.4187") and returns a canonical decimal string ("5000", "5000.5").
 * Never goes through a float, so every digit survives. Returns null when ambiguous
 * or not a number ("1.0000", "1,2,3", "abc", "").
 */
export function parseDecimalPtBR(raw: string): string | null {
  let s = raw.replace(/\s+/g, "");
  if (!s) return null;
  let sign = "";
  if (s.startsWith("-") || s.startsWith("+")) {
    sign = s[0] === "-" ? "-" : "";
    s = s.slice(1);
  }
  if (!s) return null;

  let intPart: string;
  let fracPart = "";
  const commas = s.split(",").length - 1;
  if (commas > 1) return null;
  if (commas === 1) {
    const [left, right] = s.split(",");
    if (!/^\d+$/.test(right)) return null;
    if (left === "") intPart = "0";
    else if (PLAIN_DIGITS.test(left) || THOUSANDS_GROUPS.test(left)) intPart = left.replace(/\./g, "");
    else return null;
    fracPart = right;
  } else if (THOUSANDS_GROUPS.test(s)) {
    intPart = s.replace(/\./g, "");
  } else if (PLAIN_DIGITS.test(s)) {
    intPart = s;
  } else {
    const dots = s.split(".").length - 1;
    if (dots !== 1) return null;
    const [left, right] = s.split(".");
    if (!/^\d+$/.test(right)) return null;
    if (left !== "" && !PLAIN_DIGITS.test(left)) return null;
    // "1.0000": a dot followed by 3+ zeros only is a mistyped thousands group, not a decimal.
    if (right.length >= 3 && /^0+$/.test(right)) return null;
    intPart = left === "" ? "0" : left;
    fracPart = right;
  }

  intPart = intPart.replace(/^0+(?=\d)/, "");
  fracPart = fracPart.replace(/0+$/, "");
  const body = fracPart ? `${intPart}.${fracPart}` : intPart;
  if (body === "0") return "0";
  return `${sign}${body}`;
}
