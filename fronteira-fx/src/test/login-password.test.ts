import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { hashPassword, isWellFormedPasswordHash, parsePasswordHash, verifyPassword } from "@/lib/server/site-password";

// N baixo só nos testes para ficar rápido; o padrão de geração (N=2^15) é coberto pelo script.
const FAST = { N: 2 ** 10, r: 8, p: 1 };

describe("hash da senha do dono (scrypt)", () => {
  it("gera o formato scrypt$N$r$p$salt$hash com salt aleatório", async () => {
    const a = await hashPassword("senha-forte-123", FAST);
    const b = await hashPassword("senha-forte-123", FAST);
    expect(a).toMatch(/^scrypt\$1024\$8\$1\$[A-Za-z0-9+/=]+\$[A-Za-z0-9+/=]+$/);
    expect(a).not.toBe(b);
    expect(parsePasswordHash(a)?.key.length).toBe(32);
  });

  it("confere a senha certa e recusa a errada, vazia, parecida ou sem acento igual", async () => {
    const hash = await hashPassword("Ação & Câmbio 2026", FAST);
    expect(await verifyPassword("Ação & Câmbio 2026", hash)).toBe(true);
    expect(await verifyPassword("Ação & Câmbio 2027", hash)).toBe(false);
    expect(await verifyPassword("Ação & Câmbio 2026 ", hash)).toBe(false);
    expect(await verifyPassword("Acao & Câmbio 2026", hash)).toBe(false);
    expect(await verifyPassword("", hash)).toBe(false);
  });

  it("recusa hash mal formado, parâmetros fora dos limites e algoritmo diferente", async () => {
    const good = await hashPassword("x", FAST);
    const [, N, r, p, salt, key] = good.split("$");
    const bad = [
      "",
      "scrypt$1$2",
      `bcrypt$${N}$${r}$${p}$${salt}$${key}`,
      `scrypt$1000$${r}$${p}$${salt}$${key}`, // N não é potência de 2
      `scrypt$${2 ** 4}$${r}$${p}$${salt}$${key}`, // N abaixo do mínimo
      `scrypt$${2 ** 21}$${r}$${p}$${salt}$${key}`, // N acima do máximo
      `scrypt$${N}$99$${p}$${salt}$${key}`,
      `scrypt$${N}$${r}$0$${salt}$${key}`,
      `scrypt$${N}$${r}$${p}$!!!$${key}`,
      `scrypt$${N}$${r}$${p}$${salt}$${"A".repeat(4)}`, // chave curta demais
    ];
    for (const stored of bad) {
      expect(isWellFormedPasswordHash(stored)).toBe(false);
      expect(await verifyPassword("x", stored)).toBe(false);
    }
    expect(isWellFormedPasswordHash(good)).toBe(true);
  });

  it("o script `pnpm hash-senha` produz hash que o servidor confere (sem a senha na linha de comando)", () => {
    const script = fileURLToPath(new URL("../../scripts/hash-password.mjs", import.meta.url));
    const out = execFileSync(process.execPath, [script], { input: "senha-do-deploy\n", encoding: "utf8" }).trim();
    expect(isWellFormedPasswordHash(out)).toBe(true);
    return verifyPassword("senha-do-deploy", out).then((ok) => expect(ok).toBe(true));
  });
});
