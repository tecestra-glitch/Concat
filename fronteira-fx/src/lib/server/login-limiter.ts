/**
 * Limite de tentativas de login. Melhor esforço: vive na memória do processo, então em serverless cada
 * instância tem a sua contagem e um cold start a zera. Serve para frear tentativas por IP e um teto global
 * (cobre o caso de IP forjado no cabeçalho `x-forwarded-for`). Não substitui um WAF ou o rate limit da Vercel.
 */

export const LOGIN_MAX_FAILURES_PER_IP = 5;
export const LOGIN_MAX_FAILURES_GLOBAL = 30;
export const LOGIN_WINDOW_MS = 15 * 60 * 1000;
/** Atraso fixo aplicado a toda tentativa, certa ou errada. */
export const LOGIN_DELAY_MS = 800;

const GLOBAL_KEY = "*";
const PRUNE_AT = 5_000;

type Entry = { count: number; windowStart: number };
const failures = new Map<string, Entry>();

/** Chave do IP: primeiro valor de `x-forwarded-for`, senão `x-real-ip`, senão um balde comum. */
export function clientKey(headers: Headers): string {
  const forwarded = headers.get("x-forwarded-for")?.split(",")[0]?.trim();
  if (forwarded) return forwarded.slice(0, 64);
  return headers.get("x-real-ip")?.trim().slice(0, 64) || "desconhecido";
}

function live(key: string, now: number): Entry | undefined {
  const entry = failures.get(key);
  if (!entry) return undefined;
  if (now - entry.windowStart >= LOGIN_WINDOW_MS) {
    failures.delete(key);
    return undefined;
  }
  return entry;
}

function prune(now: number): void {
  if (failures.size < PRUNE_AT) return;
  for (const key of [...failures.keys()]) live(key, now);
}

/** Pode tentar agora? Bloqueado quando o IP ou o total da janela atingiu o teto. */
export function loginBlocked(key: string, now: number = Date.now()): boolean {
  const ip = live(key, now);
  const global = live(GLOBAL_KEY, now);
  return (ip?.count ?? 0) >= LOGIN_MAX_FAILURES_PER_IP || (global?.count ?? 0) >= LOGIN_MAX_FAILURES_GLOBAL;
}

function bump(key: string, now: number): void {
  const entry = live(key, now);
  if (entry) entry.count += 1;
  else failures.set(key, { count: 1, windowStart: now });
}

/** Registra uma falha de senha para o IP e no total. */
export function recordLoginFailure(key: string, now: number = Date.now()): void {
  prune(now);
  bump(key, now);
  bump(GLOBAL_KEY, now);
}

/** Senha certa: zera a contagem deste IP (o total segue a janela). */
export function clearLoginFailures(key: string): void {
  failures.delete(key);
}

/** Só para os testes. */
export function resetLoginLimiter(): void {
  failures.clear();
}
