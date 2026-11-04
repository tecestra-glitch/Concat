/**
 * Créditos dos elementos do Uiverse.io usados (ou previstos) em `src/components/ui/fx/`.
 * Licença de todos: MIT (repositório uiverse-io/galaxy, LICENSE: Copyright (c) 2023 Uiverse.io).
 * A mesma lista está em `docs/creditos-uiverse.md`; a página de créditos (fase 2) lê daqui.
 */
export interface UiverseCredit {
  slug: string;
  elemento: string;
  autor: string;
  licenca: "MIT";
  /** Página do elemento no Uiverse.io (autor e nome do elemento). */
  url: string;
  arquivo: string;
  uso: string;
}

export const UIVERSE_CREDITS: readonly UiverseCredit[] = [
  { slug: "botao-primario", elemento: "3bdel3ziz-T_brown-earwig-37", autor: "3bdel3ziz-T", licenca: "MIT", url: "https://uiverse.io/3bdel3ziz-T/brown-earwig-37", arquivo: "3bdel3ziz-T_brown-earwig-37.html", uso: "fase 1: variante default de ui/button.tsx" },
  { slug: "botao-secundario-flip", elemento: "mi-series_terrible-sheep-85", autor: "mi-series", licenca: "MIT", url: "https://uiverse.io/mi-series/terrible-sheep-85", arquivo: "mi-series_terrible-sheep-85.html", uso: "fase 2: Exportar e Ver detalhes (não implementado na fase 1)" },
  { slug: "botao-discreto-neumorfico", elemento: "Kabak_unlucky-treefrog-77", autor: "Kabak", licenca: "MIT", url: "https://uiverse.io/Kabak/unlucky-treefrog-77", arquivo: "Kabak_unlucky-treefrog-77.html", uso: "fase 1: variante ghost de ui/button.tsx (sem neumorfismo)" },
  { slug: "chip-estado", elemento: "kamehame-ha_swift-penguin-73", autor: "kamehame-ha", licenca: "MIT", url: "https://uiverse.io/kamehame-ha/swift-penguin-73", arquivo: "kamehame-ha_swift-penguin-73.html", uso: "fase 1: ui/fx/fx-chip.tsx (modo e status de fonte)" },
  { slug: "abas-segmentadas", elemento: "zanina-yassine_curly-shrimp-52", autor: "zanina-yassine", licenca: "MIT", url: "https://uiverse.io/zanina-yassine/curly-shrimp-52", arquivo: "zanina-yassine_curly-shrimp-52.html", uso: "fase 1: ui/fx/fx-segmented.tsx (abas do celular)" },
  { slug: "alternador", elemento: "Voxybuns_horrible-shrimp-47", autor: "Voxybuns", licenca: "MIT", url: "https://uiverse.io/Voxybuns/horrible-shrimp-47", arquivo: "Voxybuns_horrible-shrimp-47.html", uso: "fase 1: ui/switch.tsx" },
  { slug: "seletor-lista", elemento: "Na3ar-17_fast-turtle-85", autor: "Na3ar-17", licenca: "MIT", url: "https://uiverse.io/Na3ar-17/fast-turtle-85", arquivo: "Na3ar-17_fast-turtle-85.html", uso: "fase 1: ui/fx/fx-choice.tsx (seletor de par)" },
  { slug: "checkbox-circular", elemento: "faxriddin20_wicked-bobcat-36", autor: "faxriddin20", licenca: "MIT", url: "https://uiverse.io/faxriddin20/wicked-bobcat-36", arquivo: "faxriddin20_wicked-bobcat-36.html", uso: "criado na fase 1 (ui/fx/fx-checkbox.tsx); uso na fase 2" },
  { slug: "campo-entrada", elemento: "BurgiSimon_rotten-dolphin-78", autor: "BurgiSimon", licenca: "MIT", url: "https://uiverse.io/BurgiSimon/rotten-dolphin-78", arquivo: "BurgiSimon_rotten-dolphin-78.html", uso: "fase 1: ui/input.tsx e ui/select.tsx" },
  { slug: "carregador-discreto", elemento: "Bodyhc_wonderful-panther-25", autor: "Bodyhc", licenca: "MIT", url: "https://uiverse.io/Bodyhc/wonderful-panther-25", arquivo: "Bodyhc_wonderful-panther-25.html", uso: "fase 1: ui/fx/fx-spinner.tsx (dentro do cartão)" },
  { slug: "esqueleto-shimmer", elemento: "arshshaikh06_purple-sheep-4", autor: "arshshaikh06", licenca: "MIT", url: "https://uiverse.io/arshshaikh06/purple-sheep-4", arquivo: "arshshaikh06_purple-sheep-4.html", uso: "fase 1: ui/fx/fx-skeleton.tsx e ui/skeleton.tsx (brilho implementado do zero)" },
  { slug: "cartao-hover", elemento: "Admin12121_average-parrot-89", autor: "Admin12121", licenca: "MIT", url: "https://uiverse.io/Admin12121/average-parrot-89", arquivo: "Admin12121_average-parrot-89.html", uso: "fase 1: ui/fx/fx-card.tsx (cartão de oportunidade em destaque)" },
  { slug: "cartao-progresso", elemento: "Cybercom682_ordinary-duck-36", autor: "Cybercom682", licenca: "MIT", url: "https://uiverse.io/Cybercom682/ordinary-duck-36", arquivo: "Cybercom682_ordinary-duck-36.html", uso: "criado na fase 1 (ui/fx/fx-progress-card.tsx); uso na fase 2 (coleta em Fontes)" },
  { slug: "tooltip-escuro", elemento: "SouravBandyopadhyay_ugly-pug-52", autor: "SouravBandyopadhyay", licenca: "MIT", url: "https://uiverse.io/SouravBandyopadhyay/ugly-pug-52", arquivo: "SouravBandyopadhyay_ugly-pug-52.html", uso: "fase 1: ui/fx/fx-tooltip.tsx sobre ui/tooltip.tsx" },
  { slug: "padrao-grade", elemento: "adamgiebl_curvy-earwig-79", autor: "adamgiebl", licenca: "MIT", url: "https://uiverse.io/adamgiebl/curvy-earwig-79", arquivo: "adamgiebl_curvy-earwig-79.html", uso: "fase 1: ui/fx/fx-grid.tsx (fundo da home)" },
  { slug: "padrao-tile", elemento: "HarryHeywood04_ugly-squid-22", autor: "HarryHeywood04", licenca: "MIT", url: "https://uiverse.io/HarryHeywood04/ugly-squid-22", arquivo: "HarryHeywood04_ugly-squid-22.html", uso: "não implementado nas fases 1 e 2" },
];
