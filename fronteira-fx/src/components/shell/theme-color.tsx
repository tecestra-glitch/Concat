"use client";
import * as React from "react";
import { useTheme } from "next-themes";

/** Cor da barra do navegador por tema (G6): segue o tema escolhido, não `prefers-color-scheme`. */
export const THEME_COLOR = { dark: "#0b1020", light: "#f4f6fb" } as const;

/**
 * Tira o `media` dos `meta[name=theme-color]` gerados pelo Next e põe a cor do tema resolvido. O efeito só mexe no
 * DOM (nenhum estado React), então segue a regra do projeto de não usar `setState` em `useEffect`.
 */
export function ThemeColorSync() {
  const { resolvedTheme } = useTheme();
  React.useEffect(() => {
    const color = resolvedTheme === "light" ? THEME_COLOR.light : THEME_COLOR.dark;
    document.querySelectorAll<HTMLMetaElement>('meta[name="theme-color"]').forEach((meta) => {
      meta.removeAttribute("media");
      meta.content = color;
    });
  }, [resolvedTheme]);
  return null;
}
