# Mercado: notícias, referências e volatilidade (fase 1)

Esta parte do Fronteira FX acompanha o que mexe no preço do dólar e do cripto: notícias de economia, referências de
câmbio e cripto, e o quanto o preço está oscilando. Ela avisa; não compra nem vende nada.

> **Tudo aqui é referência de mercado.** Não é preço de casa de câmbio, não é cotação executável e nunca entra
> como aresta de ciclo de arbitragem. O motor de ciclos e o grafo de posições não importam este módulo.

Fonte da pesquisa que embasou esta fase: `dev/discovery/mercado.md` (fora do Git).

## O que é coletado

### Notícias (feeds públicos, sem chave)

| Fonte | Feed | Intervalo de consulta |
|---|---|---|
| Investinglive (RSS 2.0, copyright Investinglive.com) | `investinglive.com/feed/` | 60 s |
| InfoMoney | `infomoney.com.br/feed/`, `/economia/feed/`, `/mercados/feed/` | 60 s |
| Agência Brasil (economia) | `agenciabrasil.ebc.com.br/rss/economia/feed.xml` | 60 s |
| Banco Central (Copom) | comunicados e atas (Atom) | 5 min |
| MercoPress (Paraguai e economia, em inglês) | `en.mercopress.com/rss/paraguay` e `/rss/economy` | 5 min |

Guardamos **só**: título (até 300 caracteres), link para a matéria original, fonte, hora de publicação e hora de
captura. O InfoMoney reserva os direitos do texto, então **nenhum texto de matéria é guardado**.

- Investinglive: além disso guarda um **trecho curto** (até 280 caracteres, sem HTML, sem script nem estilo) e o
  `guid` do feed, só para deduplicar. Cada manchete mostra a atribuição "Fonte: Investinglive.com (copyright
  Investinglive.com)" e o link para a matéria original. Autor não é guardado.
- Itens repetidos (mesmo `guid` dentro do feed, ou mesmo link em qualquer feed) são ignorados.

### Sentimento (Fear & Greed, Alternative.me, sem chave)

- `api.alternative.me/fng/`, uma leitura por dia, consultada no máximo a cada hora. Guarda valor (0 a 100), rótulo,
  data da observação e hora da captura. Sempre com a atribuição "Fear & Greed Index: Alternative.me".
- Não é preço nem sinal de execução: `executable: false`. Sem chave, sem variável de ambiente nova.
- Os feeds `/economia/feed/` e `/mercados/feed/` do InfoMoney vieram **vazios** na conferência. Não é erro: o sistema
  trata feed vazio como lista vazia.
- Texto vindo de feed é **dado não confiável**. A tela mostra tudo como texto escapado e nenhum modelo recebe esse
  texto como instrução.
- DTD e entidades XML são recusados (proteção contra XML malicioso).

### Referências de mercado (sem chave)

| Instrumento | Fonte | Observação |
|---|---|---|
| BTC/USDT, ETH/USDT, USDT/BRL | Binance (dados públicos) | preço, variação em 24 h e velas de 5 min e de 1 dia |
| USD/BRL, USD/PYG, USD/ARS, EUR/USD | Frankfurter (dados do BCE, diários) | o BRL aqui é a referência do BCE, não a PTAX |
| PTAX venda, PTAX compra | Banco Central, séries SGS 1 e 10813 | referência oficial diária |
| Selic meta | Banco Central, série SGS 432 | confere com a decisão do Copom (13,75 % a.a. em 16/09/2026) |

Cada cotação traz `executable: false` e uma nota de referência. Ela aparece na tela com o aviso
"referência, não preço executável".

## O que não é coletado (e por quê)

| Não coletado | Motivo |
|---|---|
| Yahoo Finance | Os termos proíbem coleta automatizada. |
| X (Twitter) | Não há leitura grátis. A API paga cobra US$ 0,005 por post lido. Raspar o X dá suspensão permanente. Fica para a fase 2. |
| Valor, CNN Brasil, Bloomberg Línea, Fazenda, imprensa do Paraguai | Não há feed público confirmado. Raspar exigiria ler antes os termos de cada site. |
| Telegram com conta de usuário | Dá acesso total à conta. Só bot, na fase 2. |
| Índices mundiais (S&P 500, VIX, Ibovespa), commodities, juros futuros | Ainda não foram pesquisados provedor por provedor. Ver fase 2. |
| Operações de compra e venda, ordens | Regra do projeto: nada executa movimentação financeira. |

## Métodos de volatilidade

Os números estão em `backend/src/fronteira_fx/market/vol.py` e são testados com exemplos feitos à mão.

- **EWMA (λ = 0,94, padrão RiskMetrics):** σ² de hoje = 0,94 × σ² de ontem + 0,06 × retorno de ontem². Dá a previsão
  do desvio do próximo movimento de 5 minutos. O alerta compara o último movimento com a previsão feita **antes** dele
  (sem olhar o futuro).
- **Parkinson:** usa a máxima e a mínima de cada vela, que informam mais que só o fechamento. Não anualizado.
- **ATR(14), de Wilder:** média do "tamanho real" das velas de 5 minutos, em preço (a mesma unidade do preço, para
  dizer quanto o dólar cripto costuma andar por vela).
- **Regime:** compara a volatilidade do último dia (velas de 5 min, escaladas pela raiz do tempo) com a dos últimos 20
  dias (velas diárias).

Selo na tela:

| Selo | Quando (limiares de partida, a calibrar com dados reais) |
|---|---|
| normal | nenhum dos sinais abaixo |
| alta | regime ≥ 1,5 ou movimento acima de 2× a EWMA |
| muito alta | movimento acima de 3× a EWMA **ou** regime ≥ 2 (esse é o alerta, que também vai para o stream) |

Se faltam velas ou os dados estão velhos, o selo não aparece: a tela mostra "dados insuficientes" ou
"dados antigos". Nunca mostra um número inventado.

## Sondagem

- Cada fonte tem piso de 60 s. O worker chama a sondagem a cada tick, mas só as fontes vencidas são consultadas.
- Feeds usam requisição condicional (ETag / If-Modified-Since): sem mudança, a resposta é `304` e nada é lido.
- Erro ou bloqueio (HTTP 418/429) faz recuo exponencial com jitter.
- Só roda em `data_mode = real`. Em `demo` os dados são gerados a partir de uma semente fixa, sem rede. Em
  `simulation` não há consulta.

## Achados da conferência (fase 1)

- **Binance:** o host de negociação `api.binance.com` respondeu HTTP 451 ("serviço indisponível em local restrito")
  na máquina de conferência. Por isso o código usa o host público de dados `data-api.binance.vision`, que respondeu
  com os formatos esperados (ticker, velas, o par USDT/BRL existe). Se a instalação estiver em região restrita, use
  esse host também: ele não exige chave.
- **Códigos do BCB:** a série 432 (Selic meta) confere com o Copom. As séries 1 e 10813 (PTAX venda e compra) deram
  valores de ordem de grandeza coerente (≈ 5,42 e 5,49), mas o **nome exato no catálogo do SGS não foi lido**. Antes de
  usar essas séries em qualquer decisão, confira no catálogo oficial.
- **Frankfurter v2:** `GET /v2/rates?base=USD&quotes=…` devolve lista de `{date, base, quote, rate}`, com `rate` como
  número exato (o código lê com `Decimal`, nunca com `float`).

## Fase 2 (paga, depende de decisão sua)

Nada disso está implementado. Cada item depende de uma decisão do dono:

1. **X (API paga, pay-per-use):** cerca de US$ 30 a 50 por mês com teto de gasto e poucas contas institucionais (sem
   pessoas físicas, por causa da regra de vigilância do X). Exige conta no X Developer e cartão.
2. **Telegram (bot):** canal do InfoMoney, grátis. Exige criar o bot pelo @BotFather.
3. **Índices mundiais, commodities e juros:** exige escolher um provedor depois de confirmar a cobertura (a pesquisa
   não cobriu isso). Opções com custo: Twelve Data Grow, Tiingo ou EODHD, de cerca de US$ 20 a 80 por mês. Tiingo é só
   para uso interno (não pode mostrar o painel a terceiros).
4. **FRED (dados macro dos EUA):** grátis com chave, e exige o aviso de não endosso no rodapé.

Decisões pendentes: X pago (sim/não e teto), lista de contas, provedor de índices e orçamento, se o painel será só
seu (afeta a licença de alguns provedores), e se a execução fica para o futuro com aprovação manual em cada ordem.
