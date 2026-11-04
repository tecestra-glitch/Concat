// Port of `parse_decimal` / `try_parse_decimal` (backend/src/fronteira_fx/adapters/_http.py), locale "auto".
// Returns the normalised decimal string (what Python's `str(Decimal)` would print) or null when no number is found.

const NUM_RE = /[-+]?\d[\d.,'  ]*/;

export function parseDecimalText(input: string | null | undefined): string | null {
  if (input === null || input === undefined) return null;
  const s = String(input).replace(/ | /g, " ");
  const m = NUM_RE.exec(s);
  if (!m) return null;
  let num = m[0].replace(/ /g, "").replace(/'/g, "");
  let sign = "";
  if (num[0] === "+" || num[0] === "-") {
    sign = num[0] === "-" ? "-" : "";
    num = num.slice(1);
  }
  num = num.replace(/^[.,]+|[.,]+$/g, "");
  if (!num) return null;
  const hasDot = num.includes(".");
  const hasComma = num.includes(",");
  if (hasDot && hasComma) {
    const dec = num.lastIndexOf(",") > num.lastIndexOf(".") ? "," : ".";
    const thou = dec === "," ? "." : ",";
    num = num.split(thou).join("").split(dec).join(".");
  } else if (hasDot || hasComma) {
    const sep = hasDot ? "." : ",";
    const parts = num.split(sep);
    const grouped = parts.slice(1).every((p) => p.length === 3) && parts[0] !== undefined && parts[0].length >= 1 && parts[0].length <= 3;
    const isThousands = grouped || parts.length > 2;
    if (isThousands) {
      num = num.split(sep).join("");
    } else {
      if (parts.length > 2) return null;
      num = num.split(sep).join(".");
    }
  }
  if (!/^\d+(\.\d+)?$/.test(num)) return null;
  return sign + num;
}
