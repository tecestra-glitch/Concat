# Créditos: elementos do Uiverse.io

Os elementos de interface do Fronteira FX foram inspirados em elementos do catálogo [Uiverse.io](https://uiverse.io),
publicado no repositório [uiverse-io/galaxy](https://github.com/uiverse-io/galaxy) sob licença **MIT**
(`Copyright (c) 2023 Uiverse.io`). A cópia usada para referência fica fora do Git, em `dev/external/uiverse-galaxy`,
e nunca é executada.

Cada componente em `src/components/ui/fx/` traz no cabeçalho o slug, o elemento, o autor e a licença. A mesma lista
está em `src/components/ui/fx/credits.ts` (lida pela página de créditos da fase 2).

O código é reescrito com os tokens do app (`src/app/globals.css`). Nenhum CSS dos originais foi copiado literalmente.
Os elementos com o nome "esqueleto-shimmer" e "padrao-tile" tiveram o brilho e o padrão implementados do zero.

## Elementos

| Slug | Elemento (arquivo) | Autor | Licença | Uso no app |
|---|---|---|---|---|
| `botao-primario` | `3bdel3ziz-T_brown-earwig-37` | 3bdel3ziz-T | MIT | Fase 1: variante `default` de `ui/button.tsx` |
| `botao-secundario-flip` | `mi-series_terrible-sheep-85` | mi-series | MIT | Fase 2: Exportar e Ver detalhes |
| `botao-discreto-neumorfico` | `Kabak_unlucky-treefrog-77` | Kabak | MIT | Fase 1: variante `ghost` de `ui/button.tsx` (sem neumorfismo) |
| `chip-estado` | `kamehame-ha_swift-penguin-73` | kamehame-ha | MIT | Fase 1: `ui/fx/fx-chip.tsx` (modo e status de fonte) |
| `abas-segmentadas` | `zanina-yassine_curly-shrimp-52` | zanina-yassine | MIT | Fase 1: `ui/fx/fx-segmented.tsx` (abas do pregão e de oportunidades) |
| `alternador` | `Voxybuns_horrible-shrimp-47` | Voxybuns | MIT | Fase 1: `ui/switch.tsx` |
| `seletor-lista` | `Na3ar-17_fast-turtle-85` | Na3ar-17 | MIT | Fase 1: `ui/fx/fx-choice.tsx` (seletor de par) |
| `checkbox-circular` | `faxriddin20_wicked-bobcat-36` | faxriddin20 | MIT | Criado na fase 1 (`ui/fx/fx-checkbox.tsx`); uso na fase 2 |
| `campo-entrada` | `BurgiSimon_rotten-dolphin-78` | BurgiSimon | MIT | Fase 1: `ui/input.tsx` e `ui/select.tsx` |
| `carregador-discreto` | `Bodyhc_wonderful-panther-25` | Bodyhc | MIT | Fase 1: `ui/fx/fx-spinner.tsx` (dentro do cartão) |
| `esqueleto-shimmer` | `arshshaikh06_purple-sheep-4` | arshshaikh06 | MIT | Fase 1: `ui/fx/fx-skeleton.tsx` e `ui/skeleton.tsx` |
| `cartao-hover` | `Admin12121_average-parrot-89` | Admin12121 | MIT | Fase 1: `ui/fx/fx-card.tsx` (oportunidade em destaque) |
| `cartao-progresso` | `Cybercom682_ordinary-duck-36` | Cybercom682 | MIT | Criado na fase 1 (`ui/fx/fx-progress-card.tsx`); uso na fase 2 |
| `tooltip-escuro` | `SouravBandyopadhyay_ugly-pug-52` | SouravBandyopadhyay | MIT | Fase 1: `ui/fx/fx-tooltip.tsx` sobre `ui/tooltip.tsx` |
| `padrao-grade` | `adamgiebl_curvy-earwig-79` | adamgiebl | MIT | Fase 1: `ui/fx/fx-grid.tsx` (fundo da home) |
| `padrao-tile` | `HarryHeywood04_ugly-squid-22` | HarryHeywood04 | MIT | Não implementado nas fases 1 e 2 |

Descartados, sem uso em nenhuma fase: `Buttons/Spacious74_horrible-horse-4`, `Toggle-switches/Na3ar-17_fast-fireant-25`
e `Cards/Aryan-81_rare-rattlesnake-22`.

Os elementos foram conferidos: as cópias em `dev/ui/uiverse/` são idênticas aos originais e nenhuma tem `<script>`.
