import { createHash, timingSafeEqual } from "node:crypto";

// Placeholder prefix of `.env.example` in the backend (SEC-05): a placeholder secret is treated as unset.
export const PLACEHOLDER_PREFIX = "TROQUE_";

export function usableSecret(secret: string | undefined): string | null {
  const s = (secret ?? "").trim();
  if (!s || s.toUpperCase().startsWith(PLACEHOLDER_PREFIX)) return null;
  return s;
}

/** Bearer check in constant time. Both sides are hashed first so the comparison never depends on their length. */
export function bearerMatches(authorization: string | undefined, secret: string): boolean {
  if (!authorization) return false;
  const match = /^Bearer ([^\s]+)$/.exec(authorization.trim());
  if (!match?.[1]) return false;
  const given = createHash("sha256").update(match[1], "utf8").digest();
  const expected = createHash("sha256").update(secret, "utf8").digest();
  return timingSafeEqual(given, expected);
}
