# Terminal — mapa do frontend

Mapa das telas, componentes e hooks do frontend (`fronteira-fx/src`). Cada rota de `src/components/shell/nav.ts` tem uma linha. A tela de pregão é descrita em detalhe em `docs/pregao.md`.

## Telas

As páginas em `src/app` são finas: importam um container de `src/components` e o renderizam.

| Rota | Página (`src/app`) | Container | Arquivo do container |
|---|---|---|---|
| `/` | `src/app/page.tsx` | `Overview` | `src/components/overview.tsx` |
| `/mercados` | `src/app/mercados/page.tsx` | `Markets` | `src/components/markets/markets.tsx` |
| `/oportunidades` | `src/app/oportunidades/page.tsx` | `Opportunities` | `src/components/opportunities/opportunities.tsx` |
| `/simulador` | `src/app/simulador/page.tsx` | `Simulator` | `src/components/simulator/simulator.tsx` |
| `/contas` | `src/app/contas/page.tsx` | `Accounts` | `src/components/accounts.tsx` |
| `/fontes` | `src/app/fontes/page.tsx` | `Sources` | `src/components/sources.tsx` |
| `/monitor` | `src/app/monitor/page.tsx` | `Monitor` | `src/components/monitor/monitor.tsx` |
| `/alertas` | `src/app/alertas/page.tsx` | `Alerts` | `src/components/monitor/alerts.tsx` |
| `/diario` | `src/app/diario/page.tsx` | `Journal` | `src/components/journal.tsx` |
| `/configuracoes` | `src/app/configuracoes/page.tsx` | `SettingsPage` | `src/components/settings-page.tsx` |
| `/pregao` | `src/app/pregao/page.tsx` | `Pregao` | `src/components/pregao/pregao.tsx` |
| `/triangulos` | `src/app/triangulos/page.tsx` | `Triangulos` | `src/components/triangulador/triangulos.tsx` |
| `/global` | `src/app/global/page.tsx` | `MercadoGlobal` | `src/components/triangulador/mercado-global.tsx` |
| `/indicadores` | `src/app/indicadores/page.tsx` | `Indicadores` | `src/components/triangulador/indicadores.tsx` |
| `/noticias` | `src/app/noticias/page.tsx` | `Noticias` | `src/components/triangulador/noticias.tsx` |

As quatro telas do triangulador leem `/v1/market/*` (triângulos, cripto, referências, macro, indicadores, sentimento e
notícias) por `src/lib/api/triangulador.ts`. Todo número sai com «Executável» ou «Referência · não executável» e com
fonte e data. Nenhuma delas tem controle de ordem: `src/components/triangulador/triangulador.test.ts` confere isso no código.

A rota `/pregao` entra no menu (`nav.ts`) na integração, logo após "Mercados". Na página, o título é "Pregão" e os metadados usam `title: "Pregão"`.

## Pregão

Visão geral da tela e das regras de negócio: `docs/pregao.md`.

### Componentes (`src/components/pregao/`)

| Arquivo | Exporta | Papel |
|---|---|---|
| `pregao.tsx` | `Pregao`, `remotePanel` | Container `"use client"`: liga hooks, preferências, atalhos e derivações; monta o layout. `remotePanel`: resumo e gráfico carregam enquanto as cotações carregam e mostram o erro delas |
| `pregao-layout.tsx` | `PregaoLayout`, `MOBILE_TABS`, `nextTab`, `PregaoMobileTab`, `PregaoLayoutProps` | Grade da tela e abas do celular (Gráfico, Livro, Lista, Últimas) |
| `timeframe-bar.tsx` | `TimeframeBar`, `rovingIndex`, `TimeframeBarProps` | Radiogroup de intervalo (15 min, 1 hora, 4 horas, 1 dia) |
| `pair-selector.tsx` | `PairSelector`, `PairSelectorProps` | Radiogroup de par (USD/PYG, BRL/PYG, USD/BRL) |
| `indicator-toggles.tsx` | `IndicatorToggles`, `INDICATOR_ITEMS`, `IndicatorTogglesProps` | Toolbar de indicadores (SMA, EMA, Bandas de Bollinger, Nº de cotações) |
| `candle-chart.tsx` | `CandleChart`, `CandleChartProps`, `ReferenceLine` | Gráfico de velas (lightweight-charts), com overlays e referência |
| `candle-chart-options.ts` | `buildChartOptions`, `buildCandleOptions`, `buildVolumeOptions`, `buildLineOptions`, `toCandlestickData`, `toVolumeData`, `toLineData`, `readChartTokens`, `tokensFromGetter`, `FALLBACK_TOKENS`, `TOKEN_VARS`, `formatTick`, `chartAriaLabel` | Opções e dados do gráfico, sem React; tokens lidos de `globals.css` |
| `ticker-tape.tsx` | `TickerTape`, `tickerLabel`, `TickerTapeProps` | Fita rolante com a última cotação de cada série |
| `watchlist.tsx` | `Watchlist`, `WATCHLIST_COLUMNS`, `WatchlistProps` | Lista de séries acompanhadas, com variação, spread e tendência |
| `sparkline.tsx` | `Sparkline`, `sparklinePoints`, `trendLabel`, `SparklineProps` | Miniatura de tendência (`polyline`) |
| `book-ladder.tsx` | `BookLadder`, `splitBook`, `BookSides`, `BookLadderProps` | Livro de casas por par; referências em bloco separado |
| `latest-prints.tsx` | `LatestPrints`, `printTime`, `LatestPrintsProps` | Últimas atualizações (cotações publicadas recentes) |
| `session-clock.tsx` | `SessionClock`, `clockText`, `DEFAULT_ZONES`, `ClockZone`, `SessionClockProps` | Relógios das praças; puro, recebe `now` |
| `market-status.tsx` | `MarketStatus`, `summarizeSessions`, `formatCountdown`, `SessionSummary`, `MarketStatusProps` | Status agregado das casas e contagem regressiva; puro, recebe `now` |
| `stats-strip.tsx` | `StatsStrip`, `statsCells`, `rangePosition`, `STALE_AFTER_MS`, `StatsStripProps` | Faixa com as oito estatísticas do dia; colunas pela largura do próprio bloco (`@container`) |
| `spread-heatmap.tsx` | `SpreadHeatmap`, `heatStep`, `heatCellLabel`, `HEAT_LEGEND`, `HeatStep` | Mapa de calor de spread por casa e par |
| `cross-rate-card.tsx` | `CrossRateCard`, `crossState`, `fmtPyg`, `CrossRateCardProps` | Cartão de cruzamento BRL/PYG via USD, dentro da mesma casa |
| `shortcuts-help.tsx` | `ShortcutsHelp`, `ShortcutsList`, `groupBindings`, `keyLabel`, `ShortcutsHelpProps` | Diálogo de atalhos (`Dialog` Radix) e a lista `<dl>` pura |
| `delta.tsx` | `Delta`, `deltaText`, `directionOf`, `DeltaProps` | Variação com seta, sinal e texto para leitor de tela |
| `reference-badge.tsx` | `ReferenceBadge`, `ReferenceBadgeProps` | Selo "Referência" para BCP e dolarPy |
| `agio-badge.tsx` | `AgioBadge`, `agioLabel`, `AgioBadgeProps` | Badge de ágio contra a referência, por lado |

Os testes de componentes ficam em `src/components/pregao/__tests__/` e são feitos por `renderToStaticMarkup`.

### Biblioteca (`src/lib/pregao/`)

| Arquivo | Exporta | Papel |
|---|---|---|
| `types.ts` | `Timeframe`, `PairKey`, `Candle`, `CandleSeries`, `SessionStats`, `SessionStatus`, `HouseSession`, `BookLevel`, `TickerItem`, `Print`, `WatchlistRow`, `HeatCell`, `IndicatorState`, `ChartOverlays`, `TIMEFRAMES`, `TF_SECONDS`, `TIMEFRAME_LABEL`, `PAIRS`, `PAIR_LABEL`, `STATUS_LABEL`, `STATUS_BADGE`, `INDICATOR_DEFAULTS`, `INDICATOR_PERIODS` | Tipos e constantes do pregão, espelho do contrato Python |
| `schemas.ts` | `decStr`, `isoDate`, `TimeframeSchema`, `PairKeySchema`, `DataModeSchema`, `SessionStatusSchema`, `CandleSchema`, `CandleSeriesSchema`, `SessionStatsListSchema`, `HouseSessionsSchema` | Validação zod das respostas de `/v1/candles`, `/v1/pregao/stats` e `/v1/pregao/sessions` |
| `candles.ts` | `toDecStr`, `midOf`, `bucketStart`, `pairOf`, `pairKeyOf`, `quoteOfPair`, `baseOfPair`, `aggregateHistory`, `tailLimit` | Buckets, `mid` e agregação de velas a partir do histórico |
| `hours.ts` | `PRE_OPEN_MIN`, `houseStatus`, `isAlwaysOpen`, `localParts`, `zonedToUtc` | Algoritmo de status das casas (`open`, `pre`, `closed`, `unknown`) |
| `cross.ts` | `Leg`, `ImpliedCross`, `STALE_MS`, `legOf`, `isStale`, `midOfLeg`, `impliedBrlPyg`, `diffPct` | Cruzamento BRL/PYG via USD e diferença contra o direto |
| `keys.ts` | `quoteKey` | Chave da série de uma cotação: `Quote.series_key` (D2), com fallback reconstruído quando ausente |
| `derive.ts` | `isIncomplete`, `spreadPct`, `agioPct`, `pctChange`, `houseName`, `statusOf`, `refQuoteFor`, `refMidFor`, `toBookLevels`, `toTickerItems`, `toWatchlistRows`, `toHeatCells`, `quoteToPrint`, `defaultKeyFor` | Derivação pura de fita, livro, lista, mapa e últimas atualizações |
| `demo.ts` | `DEFAULT_SERIES_KEY`, `DEMO_HOUSES`, `DEMO_HOURS`, `DEMO_HOUSE_IDS`, `DEMO_ANCHOR`, `DEMO_VOL`, `fnv1a`, `lcg`, `demoCandles`, `demoStats`, `demoSessions`, `demoQuotesAt`, `demoBook`, `demoTicker`, `demoPrints`, `demoWatchlist`, `demoHeat` | Gerador demo determinístico; `now` sempre é parâmetro |
| `api.ts` | `fetchCandles`, `fetchStats`, `fetchSessions`, `STATS_BATCH`, `FetchOpts`, `CandleOpts` | Cliente HTTP do pregão pelo proxy `/api/fx` (`API_BASE`), com zod, `?data_mode=` do modo esperado (`real` ou `simulation`) e fallback de `/v1/history` |
| `indicators.ts` | `closes`, `sma`, `ema`, `bollinger`, `atr`, `vwapProxy`, `buildOverlays` | Indicadores (SMA, EMA, Bollinger, ATR de Wilder, VWAP-proxy) |
| `use-candles.ts` | `pregaoKeys`, `REFETCH_FAST_MS`, `REFETCH_SLOW_MS`, `refetchMsFor`, `candlesQueryOptions`, `useCandles`, `useSparklines` | Hook de velas e de miniaturas |
| `use-session-stats.ts` | `statsQueryOptions`, `statsByKey`, `useSessionStats` | Hook de estatísticas da sessão por chave |
| `use-house-sessions.ts` | `sessionsQueryOptions`, `useHouseSessions` | Hook de status das casas |
| `prints-store.ts` | `PRINTS_MAX`, `pushPrint`, `diffQuotes`, `subscribe`, `getSnapshot`, `startPrintsFeed`, `resetPrintsForTests` | Store das últimas atualizações, sem React |
| `use-prints.ts` | `usePrints`, `useDemoPrints`, `usePrintsFor`, `usePrintsFeed` | Hooks das últimas atualizações nos dois modos |
| `use-hotkeys.ts` | `HotkeyBinding`, `isTextTarget`, `inDialog`, `matchHotkey`, `useHotkeys`, `buildPregaoBindings` | Atalhos de teclado da página do pregão |
| `prefs.ts` | `PregaoPrefs`, `DEFAULT_PREFS`, `PREFS_KEY`, `parsePrefs`, `readPregaoPrefs`, `subscribePregaoPrefs`, `usePregaoPrefs`, `updatePregaoPrefs` | Preferências de intervalo e indicadores (`fx.pregao.prefs`), com `useSyncExternalStore`; valor gravado inválido volta ao padrão |
| `use-pregao-quotes.ts` | `pregaoQuotesFor`, `pregaoQuotesStatus`, `usePregaoQuotes`, `PregaoQuotes` | Cotações e fontes da tela no modo atual; em demo, `demoQuotesAt(now)` com o relógio da tela |
| `view.ts` | `buildPregaoView`, `cyclePair`, `PregaoView`, `PregaoViewInput`, `PregaoReference`, `PregaoCross` | Derivações da tela: níveis por par, série escolhida, chaves do resumo e das miniaturas, casas do mapa, linha de referência e pernas do cruzamento (mesmo contexto: casa, cidade, modalidade, filial e montante; referência nunca é perna) |

Os testes ficam em `src/lib/pregao/__tests__/`. Hooks são testados pelas suas `*QueryOptions` puras.

### Hooks e chaves de consulta

| Hook | `queryKey` | Atualização | Endpoint |
|---|---|---|---|
| `useCandles(key, tf)` | `["pregao", "candles", mode, key, tf, limit]` (`pregaoKeys.candles`) | 60 000 ms em `15m`; 300 000 ms em `1h`, `4h` e `1d` | `GET /v1/candles` |
| `useSparklines(keys, count)` | mesma forma, com `tf = "1h"` e `limit = count` (padrão 24) | 300 000 ms | `GET /v1/candles` |
| `useSessionStats(keys)` | `["pregao", "stats", mode, keys.join(",")]` (`pregaoKeys.stats`) | 60 000 ms | `GET /v1/pregao/stats` |
| `useHouseSessions()` | `["pregao", "sessions", mode]` (`pregaoKeys.sessions`) | 60 000 ms | `GET /v1/pregao/sessions` |
| `usePrintsFeed()` | sem query própria: assina o cache de consultas de cotações | sem intervalo (evento) | stream `quote.updated` (SSE), modo real |
| `useNow()` | sem query (`src/lib/use-now.ts`) | 30 000 ms | relógio local; `0` no servidor |

Todas as consultas usam `refetchOnWindowFocus: false`. Em modo `demo`, `fetchCandles`, `fetchStats` e `fetchSessions` não fazem rede e devolvem os geradores locais.

### `data-testid` do pregão

| testid | Elemento | Dono |
|---|---|---|
| `pregao-root` | raiz do container `Pregao` | Integração |
| `pregao-layout` | raiz do `PregaoLayout` | F11 |
| `pregao-tabs` | tablist mobile | F11 |
| `pregao-banner` | slot do banner (só quando há banner) | F11 |
| `pregao-demo-note` | nota de demonstração | Integração (renderizada no slot `banner`) |
| `pregao-chart` | `<figure>` do gráfico | F3 |
| `pregao-timeframe` | radiogroup de intervalo | F4 |
| `pregao-pair` | radiogroup de par | F4 |
| `pregao-indicators` | toolbar de indicadores | F4 |
| `pregao-ticker`, `pregao-ticker-item` | fita e cada item | F5 |
| `pregao-watchlist`, `pregao-watchlist-row` | lista e cada linha (`<tr>` ou `<li>`) | F6 |
| `pregao-book`, `pregao-book-side-buy`, `pregao-book-side-sell`, `pregao-book-row`, `pregao-book-reference`, `pregao-book-ref-row` | livro, lados, linhas, bloco e linhas de referência | F7 |
| `pregao-prints`, `pregao-print-row` | últimas atualizações e linhas | F8 |
| `pregao-clock`, `pregao-market-status` | relógio e status agregado | F9 |
| `pregao-stats` | resumo da sessão | F10 |
| `pregao-heatmap`, `pregao-heat-cell` | mapa de calor e células | F15 |
| `pregao-cross` | cartão de cruzamento | F14 |
| `pregao-reference-badge`, `pregao-agio-badge`, `pregao-delta` | badges e variação | W0B (criação), F16 (testes/refino) |
| `pregao-shortcuts`, `pregao-shortcuts-list` | diálogo de atalhos e a lista `<dl>` dentro dele | F17 |

Atributos `data-*` adicionais: `data-state` (`loading`, `empty`, `error`, `ready`), `data-mode`, `data-key`, `data-kind`, `data-tf`, `data-pair`, `data-indicator`, `data-side`, `data-best`, `data-step`, `data-direction`, `data-mobile-tab`, `data-day-start`, `data-tz`, `data-dup`, `data-id`, `data-badge` (`MarketStatus`), `data-compact` (`ReferenceBadge`).

## Como rodar

```bash
pnpm install --frozen-lockfile && pnpm dev                 # http://localhost:3000/pregao
pnpm typecheck && pnpm lint && pnpm test                   # tipos, lint e testes unitários
PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers pnpm test:e2e    # 1440, 1024 e 390 px
```

Sem API, a tela roda em modo demonstração. Os geradores ficam em `src/lib/pregao/demo.ts`. Regras de leitura e de negócio da tela estão em `docs/pregao.md`.
