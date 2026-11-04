# Pregão — leitura da tela

A tela **Pregão** mostra, ao vivo, as cotações que as casas de câmbio da fronteira publicam para BRL, USD e PYG. As casas são físicas (Ciudad del Este, Asunción e Pedro Juan Caballero) e digitais. Como comparação, aparecem também as referências do BCP e do dolarPy. Cada número tem origem clara: uma casa publicou aquela Compra e aquela Venda, uma referência foi publicada para comparar, ou o valor é um cálculo feito a partir dessas publicações (spread, ágio, variação, cruzamento).

A tela **não é bolsa**. Não há câmara central, livro de ofertas único nem leilão. Cada casa é um formador de mercado: publica o próprio preço de Compra e o próprio preço de Venda, independente das outras. Últimas atualizações são cotações publicadas. Não são negócios fechados. Nada na tela movimenta dinheiro. A referência (BCP, dolarPy) serve só para comparar: ela não é balcão, não é contraparte e nunca aparece como preço que se consegue pegar.

## Vocabulário

Os termos abaixo são os usados na interface, nesta documentação e nos nomes dos componentes.

| Termo na interface | Significado | Onde aparece |
|---|---|---|
| Pregão | A tela: panorama ao vivo das cotações publicadas pelas casas | título `h2`, item de navegação |
| Fita | Faixa rolante com a última cotação de cada série | `TickerTape` |
| Lista | Tabela de séries acompanhadas (uma linha por casa×cidade×par) | `Watchlist` |
| Gráfico | Velas OHLC do `mid` de uma série | `CandleChart` |
| Livro de casas | Casas ordenadas por melhor Compra e melhor Venda para um par | `BookLadder` |
| Últimas atualizações | Cotações publicadas recentemente, em ordem cronológica inversa | `LatestPrints` |
| Sessão | Horário de funcionamento de uma casa (aberta, fechada, pré-abertura, sem horário) | `MarketStatus`, `Watchlist`, `BookLadder` |
| Referência | Preço do BCP ou dolarPy, só para comparar | `ReferenceBadge` |
| Ágio | Diferença percentual entre o preço da casa e a referência, por lado | `AgioBadge` |
| Spread | `Venda − Compra`, mostrado em porcentagem do preço médio (`mid`) | `Watchlist`, `SpreadHeatmap`, `StatsStrip` |
| Compra / Venda | O que a casa paga / o que a casa cobra pela moeda-base | todos os componentes com preço |
| Intervalo | Tamanho da vela (15 min, 1 hora, 4 horas, 1 dia) | `TimeframeBar` |
| Cotações | Número de atualizações recebidas (campo `n`, `n_quotes`) | `StatsStrip`, legenda do gráfico |

**Palavras proibidas** em qualquer texto da interface, da documentação ou de nome de export: "negócios" (exceto na frase "Não são negócios fechados."), "trade", "ordem", "executar", "comprar agora", "vender agora", "book de ofertas", "volume negociado". No lugar delas use Compra e Venda, cotação publicada, atualização recebida e "Nº de cotações".

Rótulos de status (minúsculos, exatos): `open` → "aberta"; `closed` → "fechada"; `pre` → "pré-abertura"; `unknown` → "sem horário". Rótulo de cotação incompleta: "incompleta" (linha de cotação) e "incompleto" (cartão de cruzamento).

### Para quem não conhece bolsa

- **Bolsa** junta muitas ofertas num único livro, e o preço sai do encontro entre compradores e vendedores. **Aqui não há isso.** Cada casa de câmbio fixa os próprios preços e negocia com o próprio caixa. Por isso se diz que ela é um **formador de mercado**: publica sempre um preço de Compra e um de Venda para a moeda.
- O "melhor" preço da tela é o melhor entre as casas que estão publicando agora. Não é o resultado de um leilão, e cada casa continua valendo o próprio preço.
- **Compra** é o que a casa paga por uma moeda. **Venda** é o que a casa cobra por ela. Quem entrega moeda à casa recebe o preço de Compra. Quem recebe moeda da casa paga o preço de Venda.
- **Spread** é a diferença entre o que a casa cobra e o que paga, como porcentagem do preço médio. Quanto menor o spread, menor a diferença entre comprar e vender a mesma moeda naquela casa.
- **Referência** (BCP, dolarPy) é um número publicado por outra instituição, usado como régua de comparação. Não é um preço que você consegue fechar.
- **Cotação publicada** não é garantia: a casa pode ter mudado o preço depois. A idade mostrada ao lado de cada linha diz quanto tempo passou desde a última publicação.
- **Cruzamento BRL/PYG via USD** é uma conta informativa. A tela calcula quantos guaranis valem um real passando pelo dólar, dentro da mesma casa, e compara com o preço direto publicado por ela.

## Painéis e de onde vêm os dados

| Painel | Dados | Observação |
|---|---|---|
| Fita (`TickerTape`) | `/v1/quotes` + `/v1/pregao/stats` | Última cotação de cada série (casas e referências), com variação do dia |
| Lista (`Watchlist`) | `/v1/quotes` + `/v1/pregao/stats` + `/v1/candles` (1 h) | Uma linha por casa, cidade e par; a miniatura de tendência usa velas de 1 hora |
| Gráfico (`CandleChart`) | `/v1/candles` | Velas do `mid` da série escolhida, nos intervalos 15 min, 1 h, 4 h e 1 dia |
| Livro de casas (`BookLadder`) | `/v1/quotes` + `/v1/pregao/sessions` | Um par por vez; as casas aparecem em uma lista e a referência em bloco separado |
| Últimas atualizações (`LatestPrints`) | stream `quote.updated` via cache | Cada cotação publicada nova entra no topo; não é histórico de operações |
| Resumo da sessão (`StatsStrip`) | `/v1/pregao/stats` | Abertura, máxima, mínima, último, variação, número de cotações e spread médio do dia |
| Sessão e relógios (`MarketStatus`, `SessionClock`) | `/v1/pregao/sessions` | Status de cada casa pelo horário publicado; referências ficam fora da contagem |
| Mapa de spread (`SpreadHeatmap`) | derivado de `/v1/quotes` | Spread de cada casa nos três pares; referências não entram |
| Cruzamento BRL/PYG (`CrossRateCard`) | derivado de `/v1/quotes` | Usa só as duas pernas da casa selecionada |

Ao abrir a tela, o par inicial é USD/PYG, o intervalo inicial é 1 hora e a série selecionada é a primeira casa aberta do par (ou a primeira da lista, se nenhuma estiver aberta). Essas preferências ficam no navegador (`fx.pregao.prefs`); só intervalo e indicadores são guardados.

Cada painel mostra um de quatro estados, nesta precedência: **carregando** (esqueleto e o texto "Carregando…"), **erro** (aviso "Não foi possível carregar…" com o botão "Tentar de novo"), **vazio** (mensagem do próprio painel) e **pronto** (conteúdo). Cotação incompleta, com só um lado publicado, aparece como aviso "incompleta", nunca como erro.

Atualização: estatísticas e sessões são consultadas de novo a cada 60 s. O gráfico também: a cada 60 s no intervalo de 15 min e a cada 300 s nos de 1 h, 4 h e 1 dia. Ao voltar para a aba, a tela não consulta de novo.

Os três modos de dados (`real`, `simulation` e `demo`) nunca se misturam. Toda consulta filtra o modo e todo registro traz `data_mode`. Em modo demonstração, nenhum painel chama a rede (ver [Modo demonstração](#modo-demonstração)).

## Intervalos e "atualizações"

Os intervalos são **15 min, 1 hora, 4 horas e 1 dia**, e só eles. O motivo é o piso de sondagem: cada fonte é consultada no mínimo a cada 60 s. Uma vela de 1 ou 5 minutos teria poucas atualizações reais e um OHLC que parece mais preciso do que é. Por isso nenhuma vela fica abaixo de 15 minutos.

As velas são alinhadas ao epoch Unix em UTC. Uma vela de 15 min começa em 00:00, 00:15, 00:30… UTC, e a de 1 dia começa às 00:00 UTC. Por isso a vela diária não usa o corte de Assunção (ver [Sessão e corte diário](#sessão-e-corte-diário)).

Intervalos sem cotação **não são desenhados**: não há preenchimento nem repetição do último fechamento. Um vão no gráfico significa que nada foi publicado naquele intervalo, não que o preço ficou parado.

Cada vela tem estes campos:

| Campo | Significado |
|---|---|
| `o` | primeiro `mid` do intervalo |
| `h` / `l` | maior / menor `mid` do intervalo |
| `c` | último `mid` do intervalo |
| `n` | número de cotações do intervalo (o histograma "Nº de cotações") |
| `spread_avg` | média de Venda − Compra nas cotações que têm os dois lados |
| `buy_c` / `sell_c` | último Compra e último Venda publicados no intervalo |

`mid = (buy + sell) / 2` quando as duas pontas existem. Se só uma existe, o `mid` é essa ponta. Se nenhuma existe, a cotação não entra na vela.

Exemplo com quatro cotações da série `chaco:CDE:USD/PYG:cash`:

| Horário (UTC) | Compra | Venda | `mid` |
|---|---|---|---|
| 12:01 | 7320 | 7350 | 7335 |
| 12:06 | 7322 | 7352 | 7337 |
| 12:11 | 7318 | — | 7318 |
| 12:16 | 7325 | 7355 | 7340 |

Com intervalo de 15 min, a vela das 12:00 UTC tem `o 7335`, `h 7337`, `l 7318`, `c 7318`, `n 3`, `spread_avg 30`, `buy_c 7318` e `sell_c 7352`. A cotação das 12:11 conta em `n`, entra em `l` e `c` e atualiza `buy_c`, mas não entra em `spread_avg` nem em `sell_c`, porque não tem Venda. A vela das 12:15 UTC tem `o`, `h`, `l` e `c` iguais a 7340 e `n 1`. Com intervalo de 1 hora, as quatro cotações caem numa só vela.

**Sobre `n`:** é um contador de atualizações de cotação, não de dinheiro. O histograma do gráfico se chama "Nº de cotações" em tudo que aparece na tela. A tela não mede quanto foi movimentado, porque não vê operações. O nome interno do indicador é `volume`, mas esse nome não aparece no texto visível.

## Sessão e corte diário

O **resumo da sessão** (`StatsStrip`) é o dia da série. Ele começa às 00:00 no horário de Assunção (`America/Asuncion`) e vai até o momento atual. Não confundir com **sessão**, que é o horário de funcionamento de uma casa (ver [Horários das casas](#horários-das-casas)).

- **Abertura** (`open`): primeiro `mid` do dia.
- **Máxima** e **mínima** (`high`, `low`): maior e menor `mid` do dia.
- **Último** (`last`): último `mid`, com a hora em `last_at`.
- **Variação** (`change_abs`, `change_pct`): `change_abs` é o último menos a abertura. `change_pct` é essa diferença sobre a abertura, em porcentagem. Sem abertura, ou com abertura zero, a porcentagem fica sem valor.
- **Cotações** (`n_quotes`): cotações do dia com `mid` válido.
- **Spread médio** (`spread_avg`): média absoluta de Venda − Compra, na moeda de cotação.
- **Casas** (`houses`): quantas casas, não referências, publicaram o par no dia, em qualquer cidade ou canal, no mesmo modo de dados.

Exemplo: abertura 7335 e último 7340 dão variação de +5. Em porcentagem, 5 / 7335 · 100 = 0,0682 %, exibido como "+0,07 %".

Se nenhuma casa publicou no dia, os campos ficam sem valor, `n_quotes` vale 0 e `houses` vale 0.

O resumo usa o dia de Assunção. A vela diária usa o dia UTC. Por isso, o último candle diário e a abertura do resumo podem não coincidir.

## Referência, ágio e spread

BCP e dolarPy são **referência** (`kind: market_reference`). Valem estas regras:

- Referência **nunca é executável** e **nunca é contraparte**.
- Referência nunca entra nos lados Compra e Venda do livro. Ela aparece em bloco próprio, rotulado "Referência".
- Referência nunca é "melhor preço".
- Referência nunca é perna de cruzamento.

A referência usada para o ágio é a cotação de referência mais recente do mesmo par e do mesmo modo. Se as duas fontes existem, vale a do BCP antes da do dolarPy. Uma referência com mais de 24 horas é descartada e a tela mostra "sem referência".

**Ágio** é a diferença percentual entre o preço de cada casa e a referência, lado a lado:

```
agio_buy_pct  = (buy / ref_mid − 1) · 100
agio_sell_pct = (sell / ref_mid − 1) · 100
```

Ágio positivo significa que o lado da casa está acima da referência. Ágio negativo significa que está abaixo. Sem o lado ou sem referência, o ágio fica sem valor.

**Spread** é a margem da casa, medida sobre o preço médio:

```
mid = (buy + sell) / 2
spread_pct = (sell − buy) / mid · 100
```

Sem os dois lados, ou com `mid` menor ou igual a zero, o spread fica sem valor.

Exemplo: casa com Compra 5905 e Venda 5975, e BCP com `ref_mid` 5944,76.

- `mid` da casa = 5940. Spread = 70 / 5940 · 100 = **1,18 %**.
- `agio_buy_pct` = 5905 / 5944,76 − 1 = **−0,67 %**.
- `agio_sell_pct` = 5975 / 5944,76 − 1 = **+0,51 %**.

## Cruzamento BRL/PYG via USD

O cartão de cruzamento (`pregao-cross`, `CrossRateCard`) calcula quantos guaranis valem um real passando pelo dólar. Ele usa **só as duas pernas da mesma casa**: USD/PYG e USD/BRL. Nunca mistura casas e nunca usa a referência.

```
cross_buy = buy_py / sell_br
cross_sell = sell_py / buy_br
```

- `buy_py` e `sell_py`: Compra e Venda USD/PYG da casa.
- `buy_br` e `sell_br`: Compra e Venda USD/BRL da casa.

Exemplo: USD/PYG 5905 / 5975 e USD/BRL 5,40 / 5,46.

- `cross_buy` = 5905 / 5,46 = 1081,5018…
- `cross_sell` = 5975 / 5,40 = 1106,4815…

Se a casa também publica BRL/PYG direto, com 1092 de Compra e 1112 de Venda, a comparação com o cruzado é:

- `diffPct(1092, 1081,5018…)` = **+0,97 %**
- `diffPct(1112, 1106,4815…)` = **+0,50 %**

Fórmula: `diffPct(direto, implícito) = (direto / implícito − 1) · 100`.

Regras:

- As pernas vêm da casa selecionada, no mesmo contexto: mesma cidade, modalidade (dinheiro com dinheiro, conta com conta), filial e faixa de montante. O contexto da cotação não se mistura. Se a série selecionada é uma referência, o cartão usa a casa padrão do par.
- Se falta Compra ou Venda em qualquer perna, o cruzamento fica sem valor e aparece o aviso "incompleto".
- Se uma perna tem mais de 24 horas, ela aparece como desatualizada.
- O cruzamento é **informativo**. Não é cotação, não é oferta e não é executável.
- Valores em guarani são arredondados para inteiro na exibição. Os valores implícitos são guardados com 8 casas decimais.

## Horários das casas

Cada casa tem um horário publicado: dias da semana, abertura, fechamento e fuso. A tela calcula o status com base nesse horário e no relógio atual.

| Status (código) | Rótulo na tela | Quando | Badge |
|---|---|---|---|
| `open` | aberta | dentro do horário | verde (`gain`) |
| `pre` | pré-abertura | até `PRE_OPEN_MIN = 30` minutos antes da abertura | âmbar (`warn`) |
| `closed` | fechada | fora do horário | contorno (`outline`) |
| `unknown` | sem horário | casa sem horário cadastrado | contorno (`outline`) |

Regras:

- **Desconhecido nunca vira fechado.** Uma casa sem horário aparece como "sem horário", não como "fechada".
- Casas digitais com horário de 24 horas (no arquivo: ueno, Nomad e Revolut) ficam sempre abertas, sem contagem regressiva.
- Referências (BCP) ficam fora do total e da contagem de abertas.
- O resumo do topo conta só as casas físicas do par atual (as que aparecem na Lista): "1 de 6 casas físicas abertas". As digitais aparecem à parte ("2 de 2 digitais abertas"). O selo "aberto" (verde) exige casa física aberta; sem física aberta, digitais abertas mostram "só digitais" neutro. Senão mostra "pré-abertura", depois "fechado" e, por fim, "sem horário".
- `next_change_at` alimenta a contagem regressiva até a próxima mudança, no formato "N min" ou "N h NN min".
- Status é o **horário publicado** da casa. Ele não garante que a cotação esteja atual. Para isso, veja a idade ao lado de cada linha.
- Os horários do arquivo `backend/src/fronteira_fx/data/market_hours.json` vieram de pesquisa com checagem (2026-11-04). Só entram horários **confirmados** ou **corrigidos**; os demais são removidos ou marcados `verified: false`. A tabela de procedência está abaixo.
- **Referência BCP**: a janela 08:30–13:00 é a **apuração** do câmbio de referência (média ponderada das operações spot), não a hora de publicação. A hora de publicação não foi encontrada. Por isso a tela diz "Referência BCP: próxima mudança às HH:MM", e não "próxima às".
- **dolarPy** é referência de terceiros e nunca executável. O README traz um crontab de exemplo (`*/10`, 06–20 seg–sex), que não é horário de operação do serviço: sem entrada no arquivo, aparece como "sem horário".

### Procedência dos horários (checagem de 2026-11-04)

| Casa (`source_id`) | Horário usado | Fonte | Checagem | Situação |
|---|---|---|---|---|
| chaco (Cambios Chaco, CDE) | seg–sex 07:15–16:00; sáb 07:15–13:00; dom fechado. Sucursal Adrián Jara (1ª unidade de CDE na lista oficial) | https://www.cambioschaco.com.py/en/sucursales/ (página oficial, 21 unidades) | 2026-11-04 | confirmado |
| maxicambios (MaxiCambios, ASU) | seg–sáb 08:00–21:00; dom 10:00–20:00. Shopping Multiplaza, Casa Central | https://www.maxicambios.com.py/ (seção Sucursales) | 2026-11-04 | corrigido |
| bcp (BCP referência) | seg–sex 08:30–13:00 = janela de apuração (publicação não encontrada) | https://www.bcp.gov.py/webapps/web/cotizacion/monedas | 2026-11-04 | corrigido |
| ueno, nomad, revolut | 24 h (digitais; não pesquisadas nesta rodada) | — | — | `verified: false` |
| alberdi (CDE) | sem horário | site sem horários; só redes, sem horário de CDE | 2026-11-04 | inconclusivo: removido |
| norte (ASU) | sem horário | site HTTP 503 em três tentativas; sem outra fonte | 2026-11-04 | não encontrado: removido |
| bonanza (ASU) | sem horário | site sem sucursais nem horários | 2026-11-04 | não encontrado: removido |
| myd (M&D, não cadastrada) | sem horário | página oficial só com horários de redes; verificação com tela de espera | 2026-11-04 | inconclusivo: não cadastrada |
| dolarpy (referência) | sem horário | README: crontab de exemplo, não horário de operação | 2026-11-04 | corrigido só como exemplo: não cadastrada |

Diferenças de horário entre fontes, não cobertas pelo formato (uma entrada por casa):

- **chaco**: a sede (Casa Central) é ASU, mas o projeto cadastra a casa em CDE. Outras unidades têm horários diferentes (Casa Central seg–sex 08:30–17:00, sáb 09:00–12:00; Itá Ybate, Noblesse, Km7 etc.). O Instagram oficial diz "08:00 a 18:00, sábado até o mediodía" para El Pueblo, enquanto a página oficial diz 08:30–17:00 (Paseo Lambaré). Post do Facebook da "Plaza City CDE" diz 07:30–15:30, e essa unidade não consta da lista oficial. Prevalece a página oficial.
- **maxicambios**: o Facebook da Casa Central diz "08:00 a 18:00" seg–sex e "08:00 a 14:00" sáb, contra 08–21 do site. Facebook de CDE diz 07:30–17:00. Prevalece o site. O site lista 22 unidades; o arquivo guarda só a Casa Central. Pedro Juan Caballero não aparece no site.
- **bcp**: a página não informa a hora de publicação nem o fuso. Fuso `America/Asuncion` (UTC−3), sem fonte oficial contrária.

Pendências antes de publicar com mais casas: confirmar alberdi, norte, bonanza e myd com cada casa (telefone ou canal oficial) e incluí-las só com horário confirmado; checar o horário de publicação do BCP; decidir se o chaco deve ficar em ASU (sede).

## Atalhos

Atalhos ativos só na página do Pregão:

| Tecla | Grupo | Descrição |
|---|---|---|
| `1` | Gráfico | Velas de 15 minutos |
| `2` | Gráfico | Velas de 1 hora |
| `3` | Gráfico | Velas de 4 horas |
| `4` | Gráfico | Velas de 1 dia |
| `[` | Par | Par anterior |
| `]` | Par | Próximo par |
| `?` | Ajuda | Mostrar esta ajuda |
| `Esc` | Ajuda | Fechar |

Regras:

- Os atalhos são ignorados quando o foco está em campo de texto (`input`, `textarea`, `select`, `[contenteditable]`) ou dentro de um diálogo. Exceção: `Esc` e `?`, que funcionam no diálogo.
- Combinações com Ctrl, Cmd ou Alt são ignoradas.
- Os rótulos dos botões citam a tecla, por exemplo "15 min (tecla 1)" e "Par de moedas ([ e ] trocam o par)".

## Acessibilidade

- **Compra e Venda** usam cor neutra (`text-foreground`). Cor não carrega sentido sozinha.
- **Variação** traz sinal, seta e texto para leitor de tela (" subiu", " caiu" ou " estável"). Alta e baixa se distinguem pela forma, não só pela cor.
- **Cotação incompleta** aparece como aviso (`Badge variant="warn"`), nunca como erro.
- **Contraste**: texto com pelo menos 4,5:1 e marcas gráficas com pelo menos 3:1, nos dois temas.
- **Estrutura**: cada bloco é uma `section` com `aria-labelledby`. A página tem um só `h2` ("Pregão").
- **Seleção única** (intervalo e par) é um `radiogroup`, com setas, Home e End. Os indicadores são uma `toolbar` de botões `aria-pressed`.
- **Abas no celular**: `tablist` com setas, Home e End. Cada painel é `role="tabpanel"` com `aria-labelledby` apontando para a sua aba (o livro tem dois painéis, o livro e o mapa + cruzado, ambos ligados à aba Livro). Em md+ o `tablist` some, mas os painéis continuam visíveis e o nome que eles usam é o da aba oculta (o nome segue válido).
- **Tabelas** têm `th scope="col"`. A ordenação é um botão com `aria-sort` dentro do cabeçalho. Linhas selecionáveis respondem a Enter e Espaço.
- **Gráfico** é uma `figure` com `figcaption` em `sr-only` (resumo textual), sem papel de imagem: a biblioteca põe um link de atribuição dentro do gráfico e o estado de erro tem o botão "Tentar de novo", e controles dentro de uma imagem ficariam inacessíveis. A legenda é uma lista rotulada.
- **Casa fechada** leva o rótulo "fechada" (e `data-status="closed"`); no mapa de spread, a célula ganha contorno tracejado. Nada é esmaecido com opacidade, que derrubaria o contraste do texto abaixo de 4,5:1.
- **Sem `aria-live`** na fita e nas últimas atualizações, porque elas mudam a cada minuto. O estado de conexão e o modo demonstração são anunciados pelo aviso global.
- **Movimento**: a fita rolante pausa com foco ou mouse e vira lista estática com `prefers-reduced-motion`. O flash de linha nova só existe com `motion-safe:`.
- **Sequência de foco**: cabeçalho, controles (intervalo, par, indicadores), gráfico, livro, últimas atualizações, lista e fita.
- **Alvos**: botões com pelo menos 32 px em tela média ou maior e pelo menos 40 px em tela menor.
- **Diálogo de atalhos**: foco preso, `Esc` fecha e o título está presente.

## Modo demonstração

Demonstração: velas, livro e atualizações são gerados localmente e não refletem o mercado.

Em modo `demo`, a tela mostra a marca d'água **DEMONSTRAÇÃO** e a nota "Demonstração: velas, livro e atualizações são gerados localmente e não refletem o mercado.". Nenhuma chamada de rede é feita.

- **Velas** são geradas por um gerador determinístico. A semente vem de um hash FNV-1a sobre `chave:intervalo:índice`, e a sequência vem de um gerador linear congruente (LCG). A mesma chave e o mesmo intervalo sempre produzem as mesmas velas.
- **Âncoras** de preço: USD/PYG 5940, USD/BRL 5,43 e BRL/PYG 1100. Há um ciclo semanal suave em torno delas.
- **Relógio**: o gerador recebe `now` como parâmetro. Nenhuma função demo lê o relógio do sistema, exceto o ponto de entrada do backend, que usa o horário atual quando nenhum fim é informado.
- **Casas demo** (sequência fixa): Cambios Chaco, Cambios Alberdi, Cambios Norte, Bonanza Cambios, ueno, Nomad e BCP (referência).
- **Cotações demo** são recarimbadas com idade determinística entre 30 segundos e 9,5 minutos, para que a fita, o livro, a lista e o mapa de calor mostrem uma foto coerente.
- **Atualizações demo** são variações pequenas das cotações demo, listadas do mais novo para o mais antigo.

Os valores são ilustrativos. Não use a tela demo para decidir nada.

## Pendências

Decisões registradas na integração do pregão, para uma rodada futura. Nenhuma delas muda o contrato de `docs/api-contract.md`.

- **Aritmética decimal no cliente**: `src/lib/pregao/candles.ts` agrega o histórico em ponto flutuante e serializa com `toFixed(8)`; `impliedBrlPyg` e `diffPct` (`src/lib/pregao/cross.ts`) dividem em `number` antes de voltar a string decimal. O backend continua sendo a referência (`Decimal`); no cliente, isso só alimenta o gráfico e os cartões. Trocar por aritmética decimal quando houver biblioteca escolhida.
- **Spread negativo (livro cruzado)**: `spread_avg` mantém o sinal; o mapa de calor (`heatStep`) mapeia valores negativos para o degrau 1, o mesmo do spread mais estreito. Falta um tratamento visual próprio para livro cruzado.
- **Contagem regressiva**: `formatCountdown` arredonda para cima; entre 59 min e 1 s e 60 min aparece "1 h 00 min".
- **Horários com abertura antes das 00:30**: uma casa (não 24 h) com `opens` anterior a `00:30` pode receber `next_change_at` no passado durante a pré-abertura. Nenhuma casa cadastrada é afetada.
- **Supabase em modo transação (porta 6543)**: exigiria `connect_args={"prepare_threshold": None}` no `create_engine` do backend. Enquanto não houver essa mudança, `docs/deploy.md` manda usar o pooler em modo sessão (porta 5432).
- **Store de últimas atualizações**: `prints-store.ts` é global; ao trocar `real` → `demo` → `real`, as atualizações reais somem e voltam, sem se misturar com as demo.
