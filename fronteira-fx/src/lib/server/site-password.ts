/**
 * Senha do dono do Fronteira FX (login próprio). Só roda no servidor (node:crypto).
 *
 * Formato do hash guardado em `FX_SITE_PASSWORD_HASH` (seis campos separados por `$`):
 *
 *   scrypt$N$r$p$salt$hash
 *
 * - `N`, `r`, `p`: parâmetros do scrypt (inteiros; N potência de 2);
 * - `salt` e `hash`: base64 padrão. O hash tem entre 16 e 64 bytes (32 na geração).
 *
 * Gere com `pnpm hash-senha` (lê a senha do stdin). A conferência compara com `timingSafeEqual` sobre o
 * resultado do scrypt, então o tempo não revela o quanto da senha bate.
 */
import { randomBytes, scrypt, timingSafeEqual } from "node:crypto";

export const HASH_ALGORITHM = "scrypt";
/** Padrão de geração: N=2^15, r=8, p=1 (~32 MiB, dezenas de ms). */
export const DEFAULT_SCRYPT = { N: 2 ** 15, r: 8, p: 1 } as const;
const KEY_LENGTH = 32;
const SALT_LENGTH = 16;

/** Limites aceitos na conferência: um hash mal formado não consome memória além do razoável. */
const LIMITS = { minN: 2 ** 10, maxN: 2 ** 20, maxR: 32, maxP: 16, maxNR: 2 ** 20 } as const;

export type ScryptParams = { N: number; r: number; p: number };

function derive(password: string, salt: Buffer, keyLength: number, { N, r, p }: ScryptParams): Promise<Buffer> {
  return new Promise((resolve, reject) => {
    scrypt(password, salt, keyLength, { N, r, p, maxmem: 256 * N * r }, (err, key) => (err ? reject(err) : resolve(key)));
  });
}

/** Gera o hash no formato `scrypt$N$r$p$salt$hash`. Usado pelo script `hash-senha` e pelos testes. */
export async function hashPassword(password: string, params: ScryptParams = DEFAULT_SCRYPT): Promise<string> {
  const salt = randomBytes(SALT_LENGTH);
  const key = await derive(password, salt, KEY_LENGTH, params);
  return [HASH_ALGORITHM, params.N, params.r, params.p, salt.toString("base64"), key.toString("base64")].join("$");
}

type ParsedHash = ScryptParams & { salt: Buffer; key: Buffer };

/** `null` quando o texto não segue o formato ou os parâmetros saem dos limites. */
export function parsePasswordHash(stored: string): ParsedHash | null {
  const parts = stored.split("$");
  if (parts.length !== 6 || parts[0] !== HASH_ALGORITHM) return null;
  const numbers = [parts[1], parts[2], parts[3]].map((n) => (/^\d+$/.test(n) ? Number(n) : NaN));
  if (!numbers.every(Number.isSafeInteger)) return null;
  const [N, r, p] = numbers;
  if (N < LIMITS.minN || N > LIMITS.maxN || (N & (N - 1)) !== 0) return null;
  if (r < 1 || r > LIMITS.maxR || p < 1 || p > LIMITS.maxP || N * r > LIMITS.maxNR) return null;
  const salt = Buffer.from(parts[4], "base64");
  const key = Buffer.from(parts[5], "base64");
  if (salt.length < 8 || salt.toString("base64") !== parts[4]) return null;
  if (key.length < 16 || key.length > 64 || key.toString("base64") !== parts[5]) return null;
  return { N, r, p, salt, key };
}

/** O texto de configuração tem a forma esperada? (não confere senha nenhuma). */
export function isWellFormedPasswordHash(stored: string): boolean {
  return parsePasswordHash(stored) !== null;
}

/** Confere a senha contra o hash guardado. Hash inválido ou senha vazia → `false`. */
export async function verifyPassword(password: string, stored: string): Promise<boolean> {
  const parsed = parsePasswordHash(stored);
  if (!parsed || password.length === 0) return false;
  const derived = await derive(password, parsed.salt, parsed.key.length, parsed);
  return derived.length === parsed.key.length && timingSafeEqual(derived, parsed.key);
}
