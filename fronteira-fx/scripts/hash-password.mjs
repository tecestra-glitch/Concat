#!/usr/bin/env node
/**
 * Gera o valor de FX_SITE_PASSWORD_HASH a partir da senha lida do stdin. Imprime só o hash (uma linha).
 *
 *   printf '%s' 'sua senha' | pnpm hash-senha
 *   pnpm hash-senha < arquivo-com-a-senha        # o último \n do arquivo é descartado
 *
 * Formato: scrypt$N$r$p$salt$hash (ver src/lib/server/site-password.ts, que confere o mesmo formato).
 * A senha nunca vai para argumentos de linha de comando (não fica no histórico do shell nem em `ps`).
 */
import { randomBytes, scrypt } from "node:crypto";

const N = 2 ** 15;
const r = 8;
const p = 1;
const KEY_LENGTH = 32;

if (process.stdin.isTTY) {
  process.stderr.write("Envie a senha pelo stdin, ex.: printf '%s' 'sua senha' | pnpm hash-senha\n");
  process.exit(2);
}

const chunks = [];
for await (const chunk of process.stdin) chunks.push(chunk);
const password = Buffer.concat(chunks).toString("utf8").replace(/\r?\n$/, "");

if (password.length === 0) {
  process.stderr.write("Senha vazia: nada a gerar.\n");
  process.exit(1);
}

const salt = randomBytes(16);
const key = await new Promise((resolve, reject) => {
  scrypt(password, salt, KEY_LENGTH, { N, r, p, maxmem: 256 * N * r }, (err, derived) => (err ? reject(err) : resolve(derived)));
});

process.stdout.write(`scrypt$${N}$${r}$${p}$${salt.toString("base64")}$${key.toString("base64")}\n`);
