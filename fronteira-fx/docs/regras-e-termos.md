# Regras e termos: checklist BR e PY (U10)

Data de referência: 2026-11-04. Escopo: documentação. Nenhum código foi alterado.

Este documento lista regras de câmbio, cripto e tributação do Brasil (BR) e do Paraguai (PY), e os termos de uso
de cada fonte de dados, com o status de cada item. Serve de checklist antes de qualquer coleta ou modelagem de custo.

**Aviso:** este não é parecer jurídico nem contábil. Antes de modelar IOF, DeCripto ou a retenção da Res. BCB 584
no cálculo de lucro, vale revisão de contador e advogado (decisão do dono, ver `plano-triangulador.md`, seção 8).

## Legenda

Status:

- **vigente**: regra em vigor, com fonte identificada.
- **a partir de DATA**: regra com vigência futura ou já iniciada em data específica.
- **revogada**: regra sem efeito (com data de revogação quando conhecida).
- **não confirmado**: sem fonte primária lida, ou fonte secundária sem confirmação. Não usar como premissa de cálculo.

Fonte oficial lida:

- **sim**: o texto oficial (ou página oficial com o trecho relevante) foi aberto nesta rodada.
- **não**: só fonte secundária, memória ou relato de terceiro. Ou o texto oficial não pôde ser aberto (página sem conteúdo
  por renderização em JavaScript, ou bloqueio no acesso).

Limite desta leitura: a busca web (Firecrawl) estava sem crédito nesta data. As páginas oficiais foram acessadas
por HTTP direto pelo proxy. As normas do BCB e da RFB vieram como página de carcaça (sem texto), por isso
**nenhuma norma BR foi lida no texto oficial** nesta rodada.

## 1. Regras BR: câmbio e cripto

| ID | Regra | Fonte citada | Status | Data | Fonte oficial lida | Observação |
|---|---|---|---|---|---|---|
| BR-01 | Res. BCB 519 | Res. BCB 519 | não confirmado | não confirmado | não | Conteúdo não lido nesta rodada. Não há resumo verificado no plano. |
| BR-02 | Res. BCB 520 | Res. BCB 520 | não confirmado | não confirmado | não | Conteúdo não lido nesta rodada. Não há resumo verificado no plano. |
| BR-03 | Res. BCB 521: operação com cripto que envolve pagamento ou recebimento em moeda estrangeira é tratada como câmbio | Fonte secundária (plano, seção 1) | não confirmado | não confirmado | não | Divergência aberta sobre a alíquota de IOF (ver DIV-01). |
| BR-04 | Res. BCB 584/2026: retenção de até 24 h em transferências ao exterior | Fonte secundária (plano, seção 1) | a partir de 2027-01-01 | 2027-01-01 | não | Vigência informada pelo plano. Texto oficial não lido. |
| BR-05 | Res. BCB 584/2026: acima de US$ 10 mil, retenção também para transferência a carteira autocustodiada | Fonte secundária (plano, seção 1) | a partir de 2027-01-01 | 2027-01-01 | não | Mesmo caso de BR-04. Escopo exato a confirmar no texto oficial. |
| BR-06 | Binance: pedido de autorização ao BCB | Relato (plano, seção 1) | não confirmado | pedido em 2026-10-23 | não | Nenhuma autorização vigente confirmada. Não tratar a Binance como autorizada no Brasil. |
| BR-07 | IN RFB 2.291 (DeCripto): obrigação de informar operações com criptoativos | Plano, seção 1 e 7 | não confirmado | não confirmado | não | Escopo amplo ainda não confirmado (ver DIV-02). |
| BR-08 | IN RFB 1.888: revogação | Plano, seção 7 | não confirmado | divergente (ver DIV-02) | não | Data de revogação diverge entre fontes. |
| BR-09 | Tributação de pessoa física em cripto e em câmbio | Não localizada | não confirmado | não confirmado | não | Nenhuma fonte verificada. Não modelar IOF nem IR como fato. |
| BR-10 | Prazo de adequação de VASP (ref. IN 704) | Plano, seção 7 | divergente | divergente (ver DIV-03) | não | Conflito entre 20/10 e 30/10 não resolvido. |
| BR-11 | Regra interna: não haver envio de ordem nem movimentação de dinheiro | `CLAUDE.md` do projeto | vigente | 2026-11-04 | não se aplica (regra interna) | Vale para todo o projeto. |

## 2. Regras PY: câmbio e cotações

| ID | Regra | Fonte citada | Status | Data | Fonte oficial lida | Observação |
|---|---|---|---|---|---|---|
| PY-01 | DNIT RG 47/2026 (tabela mensal de cotizaciones para aduana) | Plano, seção 7; pesquisa de arbitragem | não confirmado | escopo e data corrigidos no plano, não verificados | não | Página institucional da DNIT foi acessada, mas sem texto da resolução. Ver `docs/pesquisa-cruzamento-arbitragem.md`. |
| PY-02 | Lei 6446 (Paraguai) | Não localizada | não confirmado | não confirmado | não | Não usar como premissa. |
| PY-03 | Licença de PSAV no Paraguai | Não localizada | não confirmado | não confirmado | não | Sem fonte para confirmar licença de casa de câmbio ou de cripto. |
| PY-04 | Situação da Binance no Paraguai | Fonte de consumidor (sem confirmação) | não confirmado | não confirmado | não | Não tratar como liberada. |
| PY-05 | API oficial do BCP | Não localizada | não confirmado | não confirmado | não | O BCP publica tabela diária na web. Não há API oficial confirmada. |
| PY-06 | Tabela DNIT como referência de aduana | `docs/pesquisa-cruzamento-arbitragem.md` | vigente como referência | não confirmado | não | Referência. Nunca executável. |

## 3. Divergências abertas

Estas divergências ficam abertas. Nenhuma data foi escolhida por conveniência.

| ID | Assunto | Divergência | Ação |
|---|---|---|---|
| DIV-01 | Res. BCB 521 e IOF | Duas fontes secundárias informam alíquotas ou bases de IOF diferentes. | Aberta. Ler o texto oficial e a regra de IOF antes de modelar. |
| DIV-02 | IN RFB 1.888 e DeCripto (2.291) | Uma fonte dá 01/07/2026 para a revogação da 1.888; outra dá outra data. Escopo amplo da DeCripto não confirmado. | Aberta. Ler a IN de revogação no Diário Oficial. |
| DIV-03 | Prazo de adequação de VASP (IN 704) | 20/10 contra 30/10, conforme fontes diferentes. | Aberta. Ler o texto da IN 704. |
| DIV-04 | Binance e HTTP 451 | Relato comunitário de bloqueio regional (HTTP 451) no host `api.binance.com`. Não há confirmação de que `data-api.binance.vision` serve onde o outro está bloqueado. | Aberta. Tratar 451 como desligamento da fonte, nunca contorno. |
| DIV-05 | Limites OANDA (120 req/s, 20 streams) | Vêm de busca e de página com copyright de 2019. | Aberta. Reverificar na documentação atual. |

## 4. Lista de termos a ler antes de qualquer coleta

Ler o termo antes de criar qualquer coleta. Coleta sem termo lido não entra em produção.
Status de leitura: **lida** (trecho relevante lido), **parcial** (página acessada, sem o trecho de termos),
**não lida** (não acessada ou sem texto).

| # | Fonte | Link | Status de leitura | Notas |
|---|---|---|---|---|
| 1 | Binance | https://www.binance.com/en/terms | não lida | A página retornou resposta vazia pelo proxy. Termos de market data (developers.binance.com) também não lidos. Regra de 451 e de limites ainda pendentes. |
| 2 | FRED (St. Louis Fed) | https://fred.stlouisfed.org/docs/api/terms_of_use.html | lida | Dados de terceiros: uso além do pessoal exige permissão do dono da série. Quem publicar app de terceiros deve exibir o link dos termos. Chave de API obrigatória (`FRED_API_KEY`, por variável de ambiente). |
| 3 | Dukascopy | https://www.dukascopy.com/swiss/english/terms-and-conditions/ | não lida | Link retornou 404. Página de marketwatch acessada, sem termos. Fonte fora de produção até leitura. |
| 4 | Stooq | https://stooq.com/ | não lida | Conexão recusada pelo proxy. Fonte secundária diz que agora exige chave. Fora de produção. |
| 5 | Finnhub | https://finnhub.io/docs/api | parcial | Documentação da API lida (schemas). Termos de uso não localizados nesta leitura. |
| 6 | OANDA | https://www.oanda.com/us-en/legal/ | parcial | Página legal acessada, sem cláusula de API de dados. Conta practice e token sob responsabilidade do dono. |
| 7 | Tiingo | https://www.tiingo.com/about/pricing | parcial | Página de preço carregada por JavaScript, sem texto de termos. `/about/terms` retornou 404. Plano: uso pessoal interno (fonte secundária). |
| 8 | Alpaca | https://www.alpaca.markets/legal | parcial | Página legal acessada, sem trecho de termos de market data. Documentação de market data acessada, sem termos. |

Fontes adicionais do plano, a ler antes de usar: Kraken, Foxbit, OKX (dados públicos), Frankfurter, Open Exchange Rates,
investinglive (RSS, copyright), Alternative.me (atribuição visível), brapi.dev, BCB SGS, Trading Economics,
CoinGecko, Twelve Data, Alpha Vantage, GDELT e X API. Todas com status **não lida** nesta rodada, exceto onde
o plano já registra limite de fonte secundária.

## 5. Regras de ferramentas e ambiente (vigentes, internas)

| Regra | Fonte | Status |
|---|---|---|
| Fonte com bloqueio regional (HTTP 451) é desligada, nunca contornada | `CLAUDE.md`, plano seção 7 | vigente |
| Referências (forex, índices, BCE, PTAX, FRED) são sempre não executáveis | Plano seção 1 e 7 | vigente |
| Segredos só por variável de ambiente; fonte que exige chave fica desligada sem ela | `CLAUDE.md` | vigente |
| Dinheiro em `Decimal`; na API, string decimal | `CLAUDE.md` | vigente |
| Testes sem rede (transporte mock) | Plano, unidades U01 a U09 | vigente |
| Não usar MCP comunitário da OANDA com token real antes de auditoria | Plano, seção 5 | vigente |
| yfinance e Stooq fora de produção (uso pessoal ou chave exigida) | Plano, seção 8 | vigente até confirmação do dono |

## 6. Pendências para leitura

1. Ler o texto oficial das Res. BCB 519, 520, 521 e 584 (BCB, Normativos) e registrar data de vigência de cada uma.
2. Ler a IN RFB 2.291 (DeCripto) e a IN que revoga a 1.888 (Diário Oficial da União).
3. Ler o texto da IN 704 (prazo de VASP) e resolver DIV-03.
4. Ler a RG 47/2026 da DNIT PY no texto oficial.
5. Ler os termos de Binance, Dukascopy, Stooq, Finnhub, Tiingo e Alpaca (itens 1 a 8 da seção 4).
6. Revisão de contador e advogado para IOF, DeCripto e retenção 584 antes de qualquer cálculo de lucro.
