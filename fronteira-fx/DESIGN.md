---
name: Fronteira FX
description: Terminal de câmbio escuro e denso; o número é o protagonista.
colors:
  background: "#0b1020"
  surface: "#111827"
  surface-2: "#171f33"
  surface-3: "#1f2a40"
  foreground: "#e6eaf3"
  muted: "#94a3b8"
  border: "#243049"
  control-border: "#64748b"
  accent: "#60a5fa"
  gain: "#34d399"
  loss: "#fb7185"
  warn: "#fbbf24"
  demo: "#c4b5fd"
  background-light: "#f4f6fb"
  surface-light: "#ffffff"
  foreground-light: "#0b1020"
  accent-light: "#2563eb"
typography:
  caption:
    fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif"
    fontSize: "12px"
    lineHeight: "16px"
    fontWeight: 500
  label:
    fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif"
    fontSize: "13px"
    lineHeight: "18px"
    fontWeight: 500
  body:
    fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif"
    fontSize: "14px"
    lineHeight: "20px"
    fontWeight: 400
  heading:
    fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif"
    fontSize: "16px"
    lineHeight: "24px"
    fontWeight: 600
  title:
    fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif"
    fontSize: "20px"
    lineHeight: "28px"
    fontWeight: 600
  number:
    fontFamily: "IBM Plex Mono, ui-monospace, monospace"
    fontVariantNumeric: tabular-nums
rounded:
  chip: "4px"
  control: "8px"
  surface: "12px"
  pill: "999px"
spacing:
  gutter-mobile: "16px"
  gutter-desktop: "24px"
  row-dense: "36px"
  touch-target: "44px"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "#0b1020"
    rounded: "{rounded.pill}"
    height: "36px"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.foreground}"
    rounded: "{rounded.control}"
  card:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.surface}"
  chip-status:
    rounded: "{rounded.chip}"
    height: "24px"
---

## Overview

Terminal de mesa de câmbio: denso, calmo e escuro por padrão. A moldura some; o número é o protagonista. Um único
acento (azul). Verde e vermelho indicam variação e sempre vêm com sinal e texto. O tema claro existe e segue os mesmos
tokens.

## Colors

Escuro é o padrão, em `.dark`; claro em `:root`. Os tokens estão em `src/app/globals.css`.

- Texto principal `foreground`; secundário `muted` (≥ 5,5:1 nos dois temas).
- `accent` é ação, foco e modo REAL. `gain` e `loss` sempre com sinal (▲ ▼, +, −) e texto.
- `demo` (lilás) só para modo DEMO e a faixa de demonstração. `warn` para simulação, atraso e custo incompleto.
- Bordas decorativas usam `border`. Controles usam `control-border` (≥ 3:1, WCAG 1.4.11).
- Texto sobre matiz a 14 % (`gain-soft`, `loss-soft`, `warn-soft`, `demo-soft`) é sempre `foreground`.

## Typography

Inter para texto; IBM Plex Mono só para números (`.fx-num`) e identificadores. Cinco papéis: caption (12), label (13),
body (14), heading (16), title (20). Nenhum texto menor que 12 px. Títulos com `text-wrap: balance`.

Todo dinheiro, taxa, ROI e quantidade usa `.fx-num`: tabular, alinhado à direita e sem quebra de linha. Datas e horas
relativas usam Inter com `.fx-tnum`.

## Layout

- Desktop a partir de 1024 px (`lg`): barra lateral com a navegação; o conteúdo em grade.
- Início: duas colunas em `lg` (candles e, à direita, 22 rem de oportunidades). Abaixo de `lg`, uma coluna com o
  gráfico antes da lista.
- Celular (390 px): barra inferior com quatro telas e "Mais". Nenhuma tela rola na horizontal.
- Gutter de 16 px no celular e 24 px a partir de `sm`. Alvos de toque de 44 px no celular.
- Alturas de painel por token: `--panel-h-sm` 280, `--panel-h-md` 360, `--panel-h-lg` 420.

## Elevation & Depth

Superfícies planas separadas por `border`. Sombra de nível 1 em cartões, nível 2 em tooltip e menu, nível 3 em
diálogos. Sem sombra animada.

## Shapes

Raio por papel: chip 4 px (selos e bandeiras), controle 8 px (botões, campos), superfície 12 px (cartões, diálogos),
pílula (CTA primário, switch). Bandeiras SVG com contorno de 1 px e raio de chip.

## Components

- **Botão primário**: pílula em `accent`. Secundário e ghost: borda `border`, hover em `surface-2`/`surface-3`.
- **Chip de status**: borda e fundo com o matiz a 14 %, ponto colorido e texto em `foreground`.
- **Abas segmentadas**: indicador desliza por `transform` em 200 ms; `role="tablist"` com setas.
- **Cartão de oportunidade**: superfície com linha de luz no hover (opacidade, 240 ms).
- **Fundo de grade**: `--grid-line` sobre o painel da home, decorativo.
- **Bandeiras**: SVG `aria-hidden` ao lado do código da moeda (BRL, USD, PYG, ARS, EUR); USDT tem ícone próprio.

## Do's and Don'ts

- Faça: números tabulares e sem quebra; sinal e texto junto da cor; faixa de modo sempre visível; realce curto só
  na célula que muda; foco visível de 2 px em `ring`.
- Não faça: animar preço, saldo, ROI ou qualquer valor que muda; `transition: all`; `box-shadow` animado; `hover:opacity-*`;
  mais de um acento; texto abaixo de 12 px; "lucro confirmado" quando o custo é incompleto.
