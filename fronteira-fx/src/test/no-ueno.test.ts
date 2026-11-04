import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * Guarda da fase 1 (dev/ui/spec-reforma-ui.md, seção 5, item c): o banco fechado pelo BCP (03/11/2026) saiu do
 * frontend. Nenhum arquivo de `src/` nem de `e2e/` pode citar o nome dele. O padrão é montado em tempo de execução
 * para que este arquivo não case. Backend, adaptadores e `docs/` ficam para a integração final (fase 2).
 */
const WORD = new RegExp("\\b" + "u" + "eno" + "\\b", "i");
const ROOT = new URL("../../", import.meta.url).pathname; // fronteira-fx/
const SCAN = ["src", "e2e"];
const SKIP_FILE = /\.(png|jpg|ico|woff2?)$/;

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) walk(p, out);
    else if (!SKIP_FILE.test(name)) out.push(p);
  }
  return out;
}

describe("banco fechado fora do frontend", () => {
  it("nenhum arquivo de src/ ou e2e/ cita o banco", () => {
    const hits: string[] = [];
    for (const dir of SCAN) {
      for (const file of walk(join(ROOT, dir))) {
        readFileSync(file, "utf8")
          .split("\n")
          .forEach((line, i) => {
            if (WORD.test(line)) hits.push(`${file.slice(ROOT.length)}:${i + 1}`);
          });
      }
    }
    expect(hits).toEqual([]);
  });
});
