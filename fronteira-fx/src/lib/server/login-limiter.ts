/**
 * Limite de tentativas de login. Melhor esforço: vive na memória do processo, então em serverless cada
 * instância tem a sua contagem e um cold start a zera. Serve para frear tentativas em paralelo e em sequência
 * (por IP e um teto global). Não substitui um WAF nem o rate limit da plataforma: a proteção real contra força
 * bruta é a senha forte (o hash scrypt impede a conferência offline) somada a esse limite.
 *
 * Uma tentativa é **reservada** antes de qualquer `await` (`reserveLoginAttempt`) e liberada depois
 * (`settleLoginAttempt`). A reserva conta como tentativa em andamento: requisições paralelas não passam todas
 * pela checagem com contagem zero.
 */

export const LOGIN_MAX_FAILURES_PER_IP = 5;
export const LOGIN_MAX_FAILURES_GLOBAL = 30;
export const LOGIN_WINDOW_MS = 15 * 60 * 1000;
/** Atraso fixo aplicado a toda tentativa, certa ou errada. */
export const LOGIN_DELAY_MS = 800;

const GLOBAL_KEY = "*";
const PRUNE_AT = 5_000;

/** `count`: falhas na janela. `pending`: tentativas reservadas que ainda não terminaram. */
type Entry = { count: number; pending: number; windowStart: number };
const failures = new Map<string, Entry>();

/**
 * Chave do IP: o último valor de `x-forwarded-for`, que é o IP anexado pelo proxy da plataforma. Os valores à
 * esquerda chegam do próprio cliente e podem ser forjados, então não são usados.
 */
export function clientKey(headers: Headers): string {
  const hops = (headers.get("x-forwarded-for") ?? "").split(",").map((hop) => hop.trim()).filter(Boolean);
  const last = hops[hops.length - 1];
  if (last) return last.slice(0, 64);
  return headers.get("x-real-ip")?.trim().slice(0, 64) || "desconhecido";
}

/** Entrada viva da chave. Expirada e sem reserva em andamento: remove. Expirada com reserva: zera só a janela. */
function live(key: string, now: number): Entry | undefined {
  const entry = failures.get(key);
  if (!entry) return undefined;
  if (now - entry.windowStart >= LOGIN_WINDOW_MS) {
    if (entry.pending === 0) {
      failures.delete(key);
      return undefined;
    }
    entry.count = 0;
    entry.windowStart = now;
  }
  return entry;
}

function ensure(key: string, now: number): Entry {
  const existing = live(key, now);
  if (existing) return existing;
  const fresh: Entry = { count: 0, pending: 0, windowStart: now };
  failures.set(key, fresh);
  return fresh;
}

function dropIfIdle(key: string): void {
  const entry = failures.get(key);
  if (entry && entry.count === 0 && entry.pending === 0) failures.delete(key);
}

function prune(now: number): void {
  if (failures.size < PRUNE_AT) return;
  for (const key of [...failures.keys()]) live(key, now);
}

/** Tentativas usadas na janela: falhas + reservas em andamento. */
function used(entry: Entry | undefined): number {
  return entry ? entry.count + entry.pending : 0;
}

/** Pode tentar agora? Bloqueado quando o IP ou o total da janela atingiu o teto. */
export function loginBlocked(key: string, now: number = Date.now()): boolean {
  return used(live(key, now)) >= LOGIN_MAX_FAILURES_PER_IP || used(live(GLOBAL_KEY, now)) >= LOGIN_MAX_FAILURES_GLOBAL;
}

/**
 * Reserva uma tentativa para o IP e no total. Devolve `false` (sem reservar) quando já está bloqueado.
 * Deve ser chamada de forma síncrona, antes de qualquer `await`, e sempre seguida de `settleLoginAttempt`.
 */
export function reserveLoginAttempt(key: string, now: number = Date.now()): boolean {
  prune(now);
  if (loginBlocked(key, now)) return false;
  ensure(key, now).pending += 1;
  ensure(GLOBAL_KEY, now).pending += 1;
  return true;
}

/** Fecha a reserva. Sucesso zera a contagem deste IP; falha soma uma no IP e no total. */
export function settleLoginAttempt(key: string, ok: boolean, now: number = Date.now()): void {
  const ip = live(key, now);
  if (ip) ip.pending = Math.max(0, ip.pending - 1);
  const total = live(GLOBAL_KEY, now);
  if (total) total.pending = Math.max(0, total.pending - 1);
  if (ok) {
    if (ip) ip.count = 0;
  } else {
    ensure(key, now).count += 1;
    ensure(GLOBAL_KEY, now).count += 1;
  }
  dropIfIdle(key);
  dropIfIdle(GLOBAL_KEY);
}

/** Registra uma falha de senha sem reserva prévia (IP e total). Mantido para testes de teto. */
export function recordLoginFailure(key: string, now: number = Date.now()): void {
  prune(now);
  ensure(key, now).count += 1;
  ensure(GLOBAL_KEY, now).count += 1;
}

/** Zera a contagem de falhas deste IP. */
export function clearLoginFailures(key: string): void {
  const entry = live(key, Date.now());
  if (entry) entry.count = 0;
  dropIfIdle(key);
}

/** Só para os testes. */
export function resetLoginLimiter(): void {
  failures.clear();
}
