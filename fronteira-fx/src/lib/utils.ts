import { clsx, type ClassValue } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

/**
 * Escala tipográfica do terminal (dev/ui/spec-reforma-ui.md, §2.5): caption, label, body, heading, title. São
 * tamanhos de fonte, não cores. Sem registrá-los aqui, o tailwind-merge trata `text-body` como cor e apaga a cor
 * da variante (ex.: `text-accent-foreground` do botão padrão).
 */
const twMerge = extendTailwindMerge({
  extend: {
    classGroups: {
      "font-size": [{ text: ["caption", "label", "body", "heading", "title"] }],
    },
  },
});

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
