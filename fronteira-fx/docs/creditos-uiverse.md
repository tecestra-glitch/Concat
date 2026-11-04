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

| Slug | Elemento (arquivo) | Autor | Licença | Link | Uso no app |
|---|---|---|---|---|---|
| `botao-primario` | `3bdel3ziz-T_brown-earwig-37` | 3bdel3ziz-T | MIT | [uiverse.io/3bdel3ziz-T/brown-earwig-37](https://uiverse.io/3bdel3ziz-T/brown-earwig-37) | fase 1: variante default de ui/button.tsx |
| `botao-secundario-flip` | `mi-series_terrible-sheep-85` | mi-series | MIT | [uiverse.io/mi-series/terrible-sheep-85](https://uiverse.io/mi-series/terrible-sheep-85) | fase 2: Exportar e Ver detalhes (não implementado na fase 1) |
| `botao-discreto-neumorfico` | `Kabak_unlucky-treefrog-77` | Kabak | MIT | [uiverse.io/Kabak/unlucky-treefrog-77](https://uiverse.io/Kabak/unlucky-treefrog-77) | fase 1: variante ghost de ui/button.tsx (sem neumorfismo) |
| `chip-estado` | `kamehame-ha_swift-penguin-73` | kamehame-ha | MIT | [uiverse.io/kamehame-ha/swift-penguin-73](https://uiverse.io/kamehame-ha/swift-penguin-73) | fase 1: ui/fx/fx-chip.tsx (modo e status de fonte) |
| `abas-segmentadas` | `zanina-yassine_curly-shrimp-52` | zanina-yassine | MIT | [uiverse.io/zanina-yassine/curly-shrimp-52](https://uiverse.io/zanina-yassine/curly-shrimp-52) | fase 1: ui/fx/fx-segmented.tsx (abas do celular) |
| `alternador` | `Voxybuns_horrible-shrimp-47` | Voxybuns | MIT | [uiverse.io/Voxybuns/horrible-shrimp-47](https://uiverse.io/Voxybuns/horrible-shrimp-47) | fase 1: ui/switch.tsx |
| `seletor-lista` | `Na3ar-17_fast-turtle-85` | Na3ar-17 | MIT | [uiverse.io/Na3ar-17/fast-turtle-85](https://uiverse.io/Na3ar-17/fast-turtle-85) | fase 1: ui/fx/fx-choice.tsx (seletor de par) |
| `checkbox-circular` | `faxriddin20_wicked-bobcat-36` | faxriddin20 | MIT | [uiverse.io/faxriddin20/wicked-bobcat-36](https://uiverse.io/faxriddin20/wicked-bobcat-36) | criado na fase 1 (ui/fx/fx-checkbox.tsx); uso na fase 2 |
| `campo-entrada` | `BurgiSimon_rotten-dolphin-78` | BurgiSimon | MIT | [uiverse.io/BurgiSimon/rotten-dolphin-78](https://uiverse.io/BurgiSimon/rotten-dolphin-78) | fase 1: ui/input.tsx e ui/select.tsx |
| `carregador-discreto` | `Bodyhc_wonderful-panther-25` | Bodyhc | MIT | [uiverse.io/Bodyhc/wonderful-panther-25](https://uiverse.io/Bodyhc/wonderful-panther-25) | fase 1: ui/fx/fx-spinner.tsx (dentro do cartão) |
| `esqueleto-shimmer` | `arshshaikh06_purple-sheep-4` | arshshaikh06 | MIT | [uiverse.io/arshshaikh06/purple-sheep-4](https://uiverse.io/arshshaikh06/purple-sheep-4) | fase 1: ui/fx/fx-skeleton.tsx e ui/skeleton.tsx (brilho implementado do zero) |
| `cartao-hover` | `Admin12121_average-parrot-89` | Admin12121 | MIT | [uiverse.io/Admin12121/average-parrot-89](https://uiverse.io/Admin12121/average-parrot-89) | fase 1: ui/fx/fx-card.tsx (cartão de oportunidade em destaque) |
| `cartao-progresso` | `Cybercom682_ordinary-duck-36` | Cybercom682 | MIT | [uiverse.io/Cybercom682/ordinary-duck-36](https://uiverse.io/Cybercom682/ordinary-duck-36) | criado na fase 1 (ui/fx/fx-progress-card.tsx); uso na fase 2 (coleta em Fontes) |
| `tooltip-escuro` | `SouravBandyopadhyay_ugly-pug-52` | SouravBandyopadhyay | MIT | [uiverse.io/SouravBandyopadhyay/ugly-pug-52](https://uiverse.io/SouravBandyopadhyay/ugly-pug-52) | fase 1: ui/fx/fx-tooltip.tsx sobre ui/tooltip.tsx |
| `padrao-grade` | `adamgiebl_curvy-earwig-79` | adamgiebl | MIT | [uiverse.io/adamgiebl/curvy-earwig-79](https://uiverse.io/adamgiebl/curvy-earwig-79) | fase 1: ui/fx/fx-grid.tsx (fundo da home) |
| `padrao-tile` | `HarryHeywood04_ugly-squid-22` | HarryHeywood04 | MIT | [uiverse.io/HarryHeywood04/ugly-squid-22](https://uiverse.io/HarryHeywood04/ugly-squid-22) | não implementado nas fases 1 e 2 |

Descartados, sem uso em nenhuma fase: `Buttons/Spacious74_horrible-horse-4`, `Toggle-switches/Na3ar-17_fast-fireant-25`
e `Cards/Aryan-81_rare-rattlesnake-22`.

Os elementos foram conferidos: as cópias em `dev/ui/uiverse/` são idênticas aos originais e nenhuma tem `<script>`.

## Licença

Os elementos do catálogo uiverse-io/galaxy são distribuídos sob a licença MIT abaixo, cópia integral de
`dev/external/uiverse-galaxy/LICENSE`. O aviso de copyright e a permissão ficam em qualquer cópia ou parte substancial
do código, como a licença exige.

```text
MIT License

Copyright (c) 2023 Uiverse.io

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
