import { describe, expect, it } from "vitest";
import { bearerMatches, usableSecret } from "../src/auth.js";
import { parseDecimalText } from "../src/decimal.js";
import { extractSummary, looksBlocked } from "../src/summary.js";
import { LIVE_BODY } from "./fake-page.js";

describe("parseDecimalText (mesma regra do parse_decimal do backend)", () => {
  it.each([
    ["5,401,871.00", "5401871.00"],
    ["1,080.3741", "1080.3741"],
    ["5.4043", "5.4043"],
    ["7.350,00", "7350.00"],
    ["7,350", "7350"],
    ["Gs. 5.680", "5680"],
    ["5000", "5000"],
  ])("%s -> %s", (input, expected) => {
    expect(parseDecimalText(input)).toBe(expected);
  });

  it("returns null when there is no number", () => {
    expect(parseDecimalText("abc")).toBeNull();
    expect(parseDecimalText("")).toBeNull();
    expect(parseDecimalText(null)).toBeNull();
  });
});

describe("extractSummary (mesmo texto ao vivo do teste Python)", () => {
  it("reads fee, list fee, rate, delivery and promo", () => {
    const s = extractSummary(LIVE_BODY);
    expect(s.fee_brl).toBe("0.00");
    expect(s.fee_before_discount_brl).toBe("45.00");
    expect(s.exchange_rate).toBe("1,080.3741");
    expect(s.delivery).toBe("0-4 Dias úteis");
    expect(s.promo).toBe("100% de desconto 45.00 BRL");
    expect(s.summary_text.startsWith("RESUMO")).toBe(true);
    expect(s.summary_text.length).toBeLessThanOrEqual(1500);
  });

  it("returns nulls for text without the summary", () => {
    const s = extractSummary("nada útil aqui");
    expect(s.fee_brl).toBeNull();
    expect(s.exchange_rate).toBeNull();
    expect(s.delivery).toBeNull();
    expect(s.promo).toBeNull();
  });
});

describe("looksBlocked", () => {
  it("detects the block words, case-insensitively", () => {
    expect(looksBlocked("Access Denied: You don't have permission")).toBe(true);
    expect(looksBlocked("Unusual traffic from your network")).toBe(true);
    expect(looksBlocked("Valor a enviar")).toBe(false);
  });
});

describe("bearerMatches / usableSecret", () => {
  const secret = "segredo-de-teste-123";

  it("accepts the exact bearer token only", () => {
    expect(bearerMatches(`Bearer ${secret}`, secret)).toBe(true);
    expect(bearerMatches(`Bearer ${secret}x`, secret)).toBe(false);
    expect(bearerMatches(`Bearer ${secret.slice(0, 5)}`, secret)).toBe(false);
    expect(bearerMatches(`Basic ${secret}`, secret)).toBe(false);
    expect(bearerMatches(undefined, secret)).toBe(false);
    expect(bearerMatches("Bearer ", secret)).toBe(false);
  });

  it("treats empty and placeholder secrets as unset", () => {
    expect(usableSecret(undefined)).toBeNull();
    expect(usableSecret("   ")).toBeNull();
    expect(usableSecret("TROQUE_ESTA_CHAVE")).toBeNull();
    expect(usableSecret(` ${secret} `)).toBe(secret);
  });
});
