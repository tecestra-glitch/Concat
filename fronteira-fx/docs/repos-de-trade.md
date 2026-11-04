# Repositórios e listas awesome de trade (U11 do triangulador)

Data da pesquisa: 2026-11-04. Escopo: swing trade, forex, arbitragem, notícias com tendência e listas awesome.
Este documento é só de referência. Nada foi clonado, instalado ou executado. Nenhum código de terceiros entra no projeto.

## Método e limites

- Firecrawl `firecrawl_developer_search` retornou HTTP 402 (sem crédito). A descoberta foi feita com WebSearch. A conferência foi feita com WebFetch nas páginas do GitHub.
- LICENSE: lida no arquivo `LICENSE` (ou `COPYING`/`LICENSE.md`) via `raw.githubusercontent.com`, na branch padrão indicada. Quando o arquivo não foi lido, a coluna diz "não lida" e o motivo.
- Data do último commit: primeiro cabeçalho "Commits on <data>" da página `/commits/` da branch padrão, lido em 2026-11-04.
- `gh api` não tem acesso a repositórios fora da sessão (HTTP 403), por isso a leitura foi pela web.
- Estrelas: as lidas nas páginas do GitHub nesta data.

Status de uso: **REF** = só referência de arquitetura, sem copiar código. **NÃO USAR** = licença ou regra de uso impede o uso no projeto. **REF-DADOS** = referência de dados, a confirmar termos antes de qualquer uso. **PENDENTE** = licença ou data não confirmadas nesta rodada.

## Tabela principal

| Projeto | URL | Estrelas | Licença (arquivo LICENSE) | Último commit | Status | Motivo |
|---|---|---|---|---|---|---|
| freqtrade | https://github.com/freqtrade/freqtrade | 56.4k | GPL-3.0 (LICENSE em `develop`) | 2026-11-03 | REF | Bot de execução. GPL: não copiar código. A metodologia de lookahead e repintura serve de referência |
| Hummingbot | https://github.com/hummingbot/hummingbot | 20.9k | Apache-2.0 (LICENSE em `master`) | 2026-09-22 | REF | Conectores e modelo cross-exchange. Executa ordens |
| Jesse | https://github.com/jesse-ai/jesse | 8.8k | MIT (LICENSE em `master`, "Copyright (c) 2020 Jesse.Trade") | 2026-11-03 | REF | Backtest e métricas. Foco em execução |
| NautilusTrader | https://github.com/nautechsystems/nautilus_trader | 31.2k | LGPL-3.0 (LICENSE em `develop`) | 2026-11-04 | REF | Motor event-driven. LGPL: referência, sem copiar |
| QuantConnect Lean | https://github.com/QuantConnect/Lean | 22.4k | Apache-2.0 (LICENSE em `master`) | 2026-11-02 | REF | Motor pesado de backtest e eventos. Não reaproveitar |
| OpenBB Platform | https://github.com/OpenBB-finance/OpenBB | 75.1k | Apache-2.0 (LICENSE em `main`, "Copyright 2021-2026 OpenBB Inc.") | 2026-11-02 | REF-DADOS | Modelo de provedores de dados. Dependências grandes |
| TradingAgents | https://github.com/TauricResearch/TradingAgents | 120.5k | Apache-2.0 (LICENSE em `main`) | 2026-10-27 | REF | Multiagente com LLM. Só como ideia para RAG, sem decisão automática |
| FinRL | https://github.com/AI4Finance-Foundation/FinRL | 17.0k | MIT (LICENSE em `master`) | 2026-10-25 | REF | Ambiente de RL para estudo. Não usar para decisão real |
| ai-hedge-fund | https://github.com/virattt/ai-hedge-fund | 64.5k | MIT (LICENSE em `main`, "Copyright (c) 2024 Virat Singh") | 2026-11-03 | NÃO USAR | Licença MIT, mas o README declara uso educacional (dado de repos.md, não relido nesta rodada) |
| FinGPT | https://github.com/AI4Finance-Foundation/FinGPT | 21.5k | MIT (LICENSE em `master`, "Copyright (c) 2024 AI4Finance Foundation Inc.") | não lida | REF | Só ideia de sentimento com LLM. Data do último commit pendente |
| backtrader | https://github.com/mementum/backtrader | 23.7k | não lida (LICENSE e COPYING retornaram 404 em `master`; repos.md indica GPL-3.0) | 2023-04-19 | NÃO USAR | GPL e sem atividade desde 2023 |
| vectorbt | https://github.com/polakowo/vectorbt | 9.7k | Commons Clause v1.0 sobre Apache-2.0 (LICENSE.md em `master`) | 2026-11-03 | NÃO USAR | A cláusula Commons Clause proíbe vender produto derivado do software |
| backtesting.py | https://github.com/kernc/backtesting.py | 9.2k | AGPL-3.0 (LICENSE.md em `master`) | 2026-08-05 | REF | AGPL: copyleft forte e uso como serviço exige cuidado. Só referência |
| tulipy | https://github.com/cirla/tulipy | 93 | LGPL-3.0 (LICENSE em `master`) | 2019-04-11 | NÃO USAR | Sem manutenção recente |
| TA-Lib | https://github.com/ta-lib/ta-lib | 1.7k | BSD (texto de redistribuição em `main`, "Copyright (c) 1999-2026, Mario Fortier"; repos.md indica BSD-3) | 2026-11-03 | REF-DADOS | Indicadores padrão. Dependência nativa em C. Licença confirmada como BSD |
| ta (bukosabino) | https://github.com/bukosabino/ta | 5.2k | não lida (repos.md indica MIT) | não lida | PENDENTE | Indicadores em pandas. Confirmar LICENSE e commit antes de uso |
| FinNews | https://github.com/scaratozzolo/FinNews | 58 | MIT (LICENSE em `master`, "Copyright (c) 2020 Scott Caratozzolo") | 2020-05-27 | REF | Coleta de RSS financeiro. Sem commit desde 2020: desatualizado |
| jiji2 | https://github.com/unageanu/jiji2 | 250 | não lida (LICENSE em `master` e `main` retornaram 404; a página mostra texto MIT sem rótulo) | 2019-01-22 | PENDENTE | Framework de forex com OANDA. Sem commit desde 2019 |
| FXBot | https://github.com/trentstauff/fxbot | 320 | não lida (LICENSE em `master` e `main` retornaram 404) | 2025-06-01 | NÃO USAR | Trading automático real com OANDA, sem licença confirmada |

## Listas awesome e índices

| Lista | URL | Estrelas | Licença (arquivo LICENSE) | Último commit | Status | Motivo |
|---|---|---|---|---|---|---|
| awesome-quant | https://github.com/wilsonfreitas/awesome-quant | 30.5k | não lida (LICENSE em `master` retornou 404) | não lida | PENDENTE | Índice de bibliotecas. Confirmar licença e data |
| awesome-systematic-trading (paperswithbacktest) | https://github.com/paperswithbacktest/awesome-systematic-trading | 15.2k | não lida (LICENSE em `master` retornou 404) | 2026-09-28 | REF | Índice de bibliotecas e estratégias. Confirmar licença |
| awesome-ai-in-finance | https://github.com/georgezouq/awesome-ai-in-finance | 6.7k | CC0-1.0 (LICENSE em `master`, "CC0 1.0 Universal") | não lida | REF | Índice de LLM e finanças. Confirmar data |
| best-of-algorithmic-trading (merovinh) | https://github.com/merovinh/best-of-algorithmic-trading | não lida | sidebar indica CC-BY-SA-4.0 (LICENSE não lido) | não lida | PENDENTE | Lista ranqueada semanal. Confirmar LICENSE e data |
| awesome-algorithmic-trading (joelowj) | https://github.com/joelowj/awesome-algorithmic-trading | 1.0k | sidebar indica CC-BY-4.0 (LICENSE não lido) | 2019-05-21 | REF | Lista desatualizada desde 2019 |
| pytrade.org (PFund-Software-Ltd) | https://github.com/PFund-Software-Ltd/pytrade.org | não lida | não lida | não lida | PENDENTE | Achado na busca, sem leitura direta |

## Achados da busca sem leitura direta

- Forex: nenhum repositório com licença confirmada apareceu além de jiji2 e FXBot. Ambos ficam fora ou pendentes.
- Swing trade: a busca só trouxe bibliotecas gerais de backtest (backtesting.py, backtrader, vectorbt, PyBacktest). Não houve repositório dedicado a swing trade com licença confirmada. PyBacktest não foi conferido.
- Notícias com tendência: a busca trouxe FinNews (MIT, parado desde 2020). Não houve lista de sentimento ou tendência com atividade recente confirmada.
- Agregadores (awesome.ecosyste.ms) não contam como fonte de licença. Não foram usados como dado.

## Pendências desta rodada

1. Ler LICENSE e data do último commit de: FinGPT (data), awesome-quant, awesome-systematic-trading (licença), best-of-algorithmic-trading, pytrade.org, ta, jiji2 e FXBot (licença).
2. Confirmar licença de backtrader (LICENSE e COPYING em 404 na `master`; tentar a branch real).
3. Retomar `firecrawl_developer_search` quando houver crédito, para buscas por repositório com `skills` e por tópico.
4. URLs de repos.md que retornaram 404 (coinpaprika/awesome-crypto-trading-bots, pandas-ta) continuam não confirmadas.

## Regras para uso

- Nenhum item é dependência do produto nesta fase. Usar só como referência de arquitetura ou de metodologia.
- Qualquer item que entrar no projeto depende de leitura da LICENSE na data de uso e de decisão do dono.
- Repositórios que executam ordens (freqtrade, Hummingbot, Jesse, Nautilus, Lean, FXBot) não são integrados. O Fronteira FX não envia ordens.
