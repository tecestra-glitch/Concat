import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { Tag } from "./shared";

const ROOT = new URL("../../", import.meta.url).pathname;
const SCREEN_DIRS = [join(ROOT, "app/triangulos"), join(ROOT, "app/global"), join(ROOT, "app/indicadores"), join(ROOT, "app/noticias"), join(ROOT, "components/triangulador")];

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) return sourceFiles(p);
    return /\.(tsx?|ts)$/.test(name) && !/\.test\./.test(name) ? [p] : [];
  });
}

describe("rótulo visível em todo número", () => {
  it("referência mostra o rótulo não executável", () => {
    const html = renderToStaticMarkup(React.createElement(Tag, { executable: false }));
    expect(html).toContain("Referência · não executável");
    expect(html).not.toContain("Executável");
  });

  it("executável mostra só o rótulo executável", () => {
    const html = renderToStaticMarkup(React.createElement(Tag, { executable: true }));
    expect(html).toContain(">Executável<");
    expect(html).not.toContain("não executável");
  });
});

describe("nenhum botão de ordem nas telas do triangulador (busca no código)", () => {
  const ORDER_WORDS = /\b(comprar|vender|enviar ordem|ordem de|buy|sell|place order|executar ordem)\b/i;

  for (const file of SCREEN_DIRS.flatMap((d) => sourceFiles(d))) {
    it(`${file.slice(ROOT.length)} não tem controle de ordem`, () => {
      const src = readFileSync(file, "utf8");
      // texto de botão, aria-label ou title de qualquer controle
      const controls = src.match(/<(button|Button|a|Link)\b[\s\S]*?>[\s\S]*?<\/(button|Button|a|Link)>/g) ?? [];
      const attrs = src.match(/(aria-label|title)=\{?"[^"]*"/g) ?? [];
      for (const c of [...controls, ...attrs]) {
        expect(ORDER_WORDS.test(c), `controle suspeito em ${file}: ${c.slice(0, 120)}`).toBe(false);
      }
    });
  }
});
