import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { describe, expect, it } from "vitest";
import { UIVERSE_CREDITS } from "@/components/ui/fx/credits";

const ROOT = process.cwd();
const doc = readFileSync(join(ROOT, "docs/creditos-uiverse.md"), "utf8");

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const p = join(dir, name);
    return statSync(p).isDirectory() ? walk(p) : [p];
  });
}

describe("créditos Uiverse.io (spec §4)", () => {
  it("cada elemento tem link do Uiverse.io com autor e nome do elemento", () => {
    for (const c of UIVERSE_CREDITS) {
      expect(c.url, c.slug).toBe(`https://uiverse.io/${c.autor}/${c.elemento.split("_").slice(1).join("_")}`);
      expect(doc, c.slug).toContain(c.url);
    }
  });

  it("docs/creditos-uiverse.md traz o texto completo da licença MIT", () => {
    expect(doc).toContain("MIT License");
    expect(doc).toContain("Copyright (c) 2023 Uiverse.io");
    expect(doc).toContain("Permission is hereby granted, free of charge, to any person obtaining a copy");
    expect(doc).toContain('THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND');
  });

  it("todo arquivo que usa elemento Uiverse tem cabeçalho com slug, autor, licença e link", () => {
    const files = walk(join(ROOT, "src")).filter((f) => /\.(tsx?|ts)$/.test(f) && !f.endsWith(".test.ts") && !f.endsWith(".test.tsx"));
    const withCredit = files.filter((f) => readFileSync(f, "utf8").includes("Crédito Uiverse.io"));
    expect(withCredit.length).toBeGreaterThanOrEqual(16);
    for (const f of withCredit) {
      const text = readFileSync(f, "utf8");
      const line = text.split("\n").find((l) => l.includes("Crédito Uiverse.io")) ?? "";
      expect(line, relative(ROOT, f)).toMatch(/slug `[^`]+`; elemento \S+; autor \S+; licença MIT; link https:\/\/uiverse\.io\/\S+/);
    }
    for (const name of ["ui/button.tsx", "ui/input.tsx", "ui/select.tsx", "ui/switch.tsx", "ui/tooltip.tsx"]) {
      expect(readFileSync(join(ROOT, "src/components", name), "utf8"), name).toContain("Crédito Uiverse.io");
    }
  });
});
