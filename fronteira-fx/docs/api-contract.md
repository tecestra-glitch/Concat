# Fronteira FX — contrato da API v1 (fonte da verdade compartilhada)

Frontend (Next.js) e backend (FastAPI) implementam exatamente estes formatos.
Todos os valores monetários trafegam como **string decimal** (ex.: `"7312.50"`) para preservar precisão;
o frontend converte só na exibição. Datas em ISO-8601 UTC. Nomes de campos sempre em `snake_case`.
`docs/openapi.json` é gerado a partir do backend (`uv run python scripts/export_openapi.py`) e deve bater com este arquivo.

Cada instância serve um único `data_mode` (`real`, `simulation` ou `demo`); todo registro devolvido carrega
`data_mode` e os modos nunca se misturam numa resposta. Toda rota `/v1` (menos `/v1/health`) aceita
`?data_mode=real|simulation|demo` opcional: é o modo que o cliente espera. Se ele diferir do modo da instância a
resposta é `409` e nada é lido nem gravado; ausente, vale o modo da instância. O frontend sempre o envia fora do
modo demonstração e descobre o modo da instância por `GET /v1/health` (que nunca o recusa). Rotas marcadas com **[chave]** exigem `X-API-Key: <chave>`
(ou `Authorization: Bearer <chave>`) quando `API_KEY` está definido no backend; sem `API_KEY`, ficam abertas.

## Enumerações

- `Currency`: `BRL | USD | PYG`
- `City`: `CDE` (Ciudad del Este) | `ASU` (Asunción) | `PJC` (Pedro Juan Caballero) | `FOZ` (Foz do Iguaçu) | `ENC` (Encarnación) | `null` (operação digital, sem cidade)
- `Channel`: `digital | physical | aggregator` (`aggregator` = agregador de terceiros, ex. dolarPy; nunca executável)
- `Modality`: `cash | transfer | account | card_debit | card_credit | card_virtual | reference` (`reference` = cotação de referência, só comparação: nunca vira aresta nem entra no ranking)
- `QuoteKind`: `market_reference | indicative | executable`
- `SourceMethod`: `official_api | html | browser | manual`
- `Health`: `ok | degraded | blocked | stale | unknown`
- `Confidence`: `quoted | estimated | incomplete`
- `DataMode`: `real | simulation | demo`
- `OpportunityKind`: `cycle | remittance_saving | purchase_saving`

## Objetos

```jsonc
Source {
  "id": "chaco", "name": "Cambios Chaco", "kind": "exchange_house|remittance|bank|fintech|central_bank",
  "method": "html", "integration": "endpoint_interno|api_oficial|html|navegador", "url": "https://...", "health": "ok", "last_success_at": "...|null", "last_error": "string|null",
  "capabilities": ["branch_table","buy_sell","usd_pyg","brl_pyg"],
  "limitations": ["sem API oficial", "cotação por filial requer navegador"],
  "coverage": { "cities": ["CDE","ASU"], "currencies": ["USD","BRL","PYG"] },
  "poll_interval_s": 300, "data_mode": "real|simulation|demo"
}
Branch { "id": "chaco-cde-centro", "source_id": "chaco", "name": "...", "city": "CDE", "address": "string|null" }
Fee { "label": "tarifa", "amount": "9.9|null", "currency": "BRL", "pct": "0.015|null" }   // fixo e/ou percentual sobre a entrada
Quote {
  "id": "uuid", "source_id": "chaco", "branch_id": "chaco-cde-centro|null", "city": "CDE|null",
  "base": "USD", "quote": "PYG",            // preço de 1 base em quote
  "buy": "7300", "sell": "7450",            // string decimal ou null; na perspectiva da casa (compra = ela compra base)
  "unit_note": "PYG por 1 USD",
  "amount_base": "5000|null",               // montante usado quando a cotação depende do valor
  "modality": "cash", "kind": "indicative", "channel": "physical|digital",
  "context": { "payment": "pix", "receive": "bank_account", "bank": null, "promo": "fee_100_off" } | null,
  "fees": [Fee],
  "captured_at": "...", "declared_updated_at": "...|null", "valid_until": "...|null",
  "evidence_id": "uuid", "data_mode": "real|simulation|demo",
  "series_key": "chaco:CDE:USD/PYG:cash"    // chave do contexto comparável (D2): `fonte:cidade|digital:BASE/QUOTE:modalidade`
                                            // + `:@filial`, `:montante`, `:ctx` quando existirem; é o `key` de /v1/history e /v1/volatility
}
HistoryPoint { "t": "...", "buy": "7300|null", "sell": "7450|null", "mid": "7375|null" }
HistorySeries { "key": "chaco:CDE:USD/PYG:cash", "points": [HistoryPoint] }
Volatility {
  "key": "...", "window": "1h|24h", "grid_s": 300, "returns_used": 11, "min_returns": 6,
  "stdev_pct_per_5m": "0.0421|null", "coverage_pct": "91.7", "gaps": 1, "status": "ok|insufficient_data|stale_input"
}
Account {
  "id": "uuid", "institution": "ueno", "label": "ueno conta USD", "currency": "USD", "kind": "bank|fintech|cash|card_debit|card_credit|card_virtual",
  "location": "ASU|CDE|PJC|digital", "balance_free": "0", "balance_reserved": "0", "balance_in_transit": "0", "updated_at": "..."
}
Position { "currency":"USD", "account_id":"uuid", "location":"digital", "modality":"account", "amount":"1000" }
RouteStep {
  "n": 1, "description": "Pix BRL → Western Union → conta ueno (PYG)",
  "from": Position, "to": Position, "rate": "1080.37|null", "rate_note": "PYG por 1 BRL",
  "amount_in": "5000", "amount_out": "5401871", "fees": [Fee], "duration": "0–4 dias úteis",
  "promo": "string|null", "confidence": "quoted|estimated|incomplete", "evidence_id": "uuid|null"
}
Opportunity {
  "id": "uuid", "title": "...", "kind": "cycle", "channel": "digital", "city": "CDE|null",
  "capital_brl": "5000", "final_value_brl": "5042.10", "net_gain_brl": "42.10", "roi": "0.00842",
  "effective_rate": "1080.37", "valuation_currency": "BRL",
  "steps": [RouteStep], "confidence": "quoted", "pending_costs": ["IOF confirmar"],
  "in_main_ranking": true, "ranking_reason": "digital com ganho líquido positivo",
  "comparable_best_digital_roi": "0.0071|null", "computed_at": "...", "data_mode": "real|simulation|demo"
}
RouteResult {                               // resposta de POST /v1/simulations/cycle
  "steps": [RouteStep], "start_currency": "BRL", "final_currency": "BRL", "valuation_currency": "BRL",
  "total_debit": "5000", "net_credit": "5042.10", "total_capital_allocated": "5000|null", "final_available": "5042.10|null",
  "effective_rate": "1.00842|null", "cycle_profit": "42.10|null", "roi": "0.00842|null", "total_fees_valued": "9.9|null",
  "confidence": "quoted|estimated|incomplete", "pending_costs": ["IOF confirmar"]
}
StepSpec {                                  // entrada de POST /v1/simulations/cycle (um passo informado pelo usuário)
  "description": "Pix → WU → ueno", "from": Position, "to": Position, "rate": "1366.5|null", "rate_note": "PYG por 1 BRL",
  "fees": [{ "label": "tarifa", "amount": "9.9|null", "currency": "BRL", "rate_to_output": "1366.5|null" }],
  "duration": "0–4 dias úteis", "promo": "string|null", "confidence": "quoted", "evidence_id": "uuid|null"
}
Evidence { "id": "uuid", "source_id": "chaco", "kind": "html|screenshot|json|manual", "url": "...", "captured_at": "...", "sha256": "...", "excerpt": "string", "rules": ["parser chaco v1"] }
JournalEntry { "id": "uuid", "ts": "...", "kind": "note|operation|reconciliation", "text": "...", "amounts": [Fee], "account_ids": [] }
StreamEvent { "id": "123", "type": "quote.updated|source.health|opportunity.updated|source.change|alert.fired|market.news|market.volatility_alert|heartbeat", "ts": "...", "payload": {} }
// payload por tipo (o stream já vem filtrado pelo data_mode da instância):
//   quote.updated       → Quote
//   source.health       → SourceHealth (atualização parcial por source_id; NÃO é um Source completo)
//   opportunity.updated → { "count": 3, "main_ranking": 1, "capitals": ["5000"] } (resumo; o cliente recarrega a lista)
//   source.change       → Change
//   alert.fired         → AlertEvent
//   market.news         → NewsItem (título, link, fonte, horários; nunca texto da matéria)
//   market.volatility_alert → MarketVolatility (só na transição para alerta, uma vez por episódio)
//   heartbeat           → {}
SourceHealth { "source_id": "chaco", "health": "blocked", "last_error": "string|null", "consecutive_failures": 2, "next_poll_at": "...|null (opcional)" }
```

## Endpoints

| Método | Rota | Descrição |
|---|---|---|
| GET | `/v1/health` | `{status, data_mode, db, version, server_time}` |
| GET | `/v1/sources` | `Source[]` |
| GET | `/v1/sources/{id}/branches` | `Branch[]` |
| GET | `/v1/quotes?city=&base=&quote=&source=&modality=&amount=` | `Quote[]` (mais recente por contexto; referências de mercado nunca viram aresta) |
| POST **[chave]** | `/v1/quotes/request` | body `{source_id, params}` → `{status:"done"|"queued"|"blocked", quote?, job_id?, reason?}`. `429` + header `Retry-After` (segundos) se a fonte foi sondada há menos de 60 s (piso por fonte, vale até para `force`) |
| GET | `/v1/history?key=&from=&to=&grid=300` | `HistorySeries` (`key` = `Quote.series_key`) |
| GET | `/v1/volatility?key=&window=1h|24h` | `Volatility` |
| GET | `/v1/candles?key=&tf=15m\|1h\|4h\|1d&from=&to=&limit=300` | `CandleSeries` — velas OHLC do `mid` de uma série (ver "Pregão") |
| GET | `/v1/pregao/stats?keys=a,b` | `SessionStats[]` — resumo do dia (00:00 Assunção) por chave, 1 a 20 chaves |
| GET | `/v1/pregao/sessions` | `HouseSession[]` — status de funcionamento por fonte, inclui referências com `reference: true` |
| GET | `/v1/institutions` | `Institution[]` — cadastro de instituições onde o titular abre conta, com a fonte de cada número (ver "Instituições") |
| GET/POST **[chave]** | `/v1/accounts` | `Account[]` / cria `Account` (POST exige chave) |
| PATCH **[chave]** | `/v1/accounts/{id}` | atualiza saldos informados manualmente |
| POST **[chave]** | `/v1/simulations/routes` | body `{capital_brl, objective:"cycle|remittance|purchase", destination?:Position, valuation_currency:"BRL", channels:["digital","physical"], amounts?:["5000","10000","25000","50000"], persist?:false}` → `{opportunities: Opportunity[], search:{amounts_tested:[string], boundaries:[{low, high, low_winner, high_winner, low_roi_sign, high_roi_sign, reason, refined}]}, simulation_id:"uuid|null"}`. Com `persist`, as linhas são gravadas com `data_mode:"simulation"` (D3) |
| POST **[chave]** | `/v1/simulations/cycle` | body `{capital:"5000", steps:[StepSpec], valuation_currency:"BRL", valuation_rates?:{"USD":"5.40"}}` → `RouteResult`. Aplica cada passo sobre o valor recebido no anterior; `422` se um passo não encadeia |
| GET | `/v1/opportunities?capital=&channel=&city=&kind=&mode=celular\|todos` | `Opportunity[]` (ranking principal + secundário). `mode` padrão `celular` (ver modo celular abaixo) |
| GET | `/v1/opportunities/cycles?max_len=4&min_roi=&start=&limit=200&mode=celular\|todos` | `Cycle[]` — ciclos no grafo de posições a partir dos saldos estacionados; `max_len` conta pernas, balcão não conta (ver abaixo); `mode` padrão `celular` |
| GET | `/v1/plans?limit=50` | `PlanOut[]` — planos de execução deste modo, do mais recente (ver "Planos de execução") |
| POST **[chave]** | `/v1/plans` | body `{start, path}` (nós de um ciclo atual de `/v1/opportunities/cycles`, até 21 nós: 6 pernas com balcões) → `201 PlanOut`; `404` se o ciclo não existe mais com as cotações e saldos atuais; `422` se o ciclo não tem ganho líquido positivo ou não tem data de cotação. Não executa nada |
| GET | `/v1/plans/{id}` | `PlanOut` (com `steps`) |
| POST **[chave]** | `/v1/plans/{id}/approve` | `PlanOut`; só grava a decisão. `409` se não estiver `proposed` ou se expirou |
| POST **[chave]** | `/v1/plans/{id}/reject` | `PlanOut`; recusa um plano `proposed` ou `approved` (antes de qualquer passo) |
| POST **[chave]** | `/v1/plans/{id}/steps/{n}/done` | body `{actual_out: "string decimal", note?: string}` → `PlanOut`. Passos em ordem, um de cada vez. Ao concluir o último, grava o resultado no diário (`kind: "result"`) |
| GET | `/v1/evidence?source=&from=&q=&limit=100` / `/v1/evidence/{id}` | `Evidence[]` / `Evidence` (`q` = substring do `excerpt`; `limit` 1..500) |
| GET/POST **[chave]** | `/v1/journal` | `JournalEntry[]` (POST exige chave) |
| GET | `/v1/snapshot` | `{cursor, quotes, sources, opportunities, server_time, data_mode}` |
| GET | `/v1/stream` | SSE. Header `Last-Event-ID` ou `?cursor=` para replay; `410 Gone` se cursor expirou → cliente refaz snapshot. O primeiro evento traz `retry:` (`STREAM_RETRY_MS`, 1000 por padrão; 30000 no modo serverless) |
| POST | `/v1/internal/collect` | rodada de coleta disparada por agendador externo, sem navegador (ver abaixo). Só com `Authorization: Bearer <CRON_SECRET>`; sem `CRON_SECRET` a rota responde `404` |

## Grafo de posições e ciclos (cruzamento ao vivo)

Nó = `"<moeda>@<venue>"` (venue: id da fonte, `fonte:cidade` para casas de câmbio, id da conta, ou `cash:<cidade>`,
com `<cidade>` em CDE, ASU, PJC, ENC, FOZ ou PPO).
Aresta = cotação (compra: base→quote a `buy`; venda: quote→base a `1/sell`), transferência (entre contas e lugares
digitais, ou entre contas e casas, priceada por `data/rails.json`), depósito/saque (balcão, ATM) ou deslocamento
(`kind: travel`, entre cidades, priceado por `data/transport.json`). Campos: `rate`, `fee_pct` (sobre a entrada),
`fee_fixed` (na moeda de saída), `iof_pct` (sobre a entrada), `transport_fixed` (deslocamento, na moeda de saída),
`minutes`, `via`, `confidence`, `evidence_id`, `quoted_at` (instante da cotação que originou a aresta; `null` em balcão,
trilho e deslocamento), `channel`, `border` (cruza BR↔PY), `ref_rate` (taxa de referência na
mesma direção de `rate`; `null` = sem referência) e `counter` (balcão: não conta em `max_len`) e `unknown_costs` (lista de `spread|fees|iof|transport` que o motor
não consegue precificar).
Aplicar as arestas de `edges[]` em ordem reproduz `amount_out`: a cada aresta,
`x = x * (1 - fee_pct - iof_pct) * rate - fee_fixed - transport_fixed`, começando em `amount_in`.
Uma aresta com deslocamento usa `transport_fixed` (não `fee_fixed`).
Balcão (ida ao caixa de uma casa na mesma cidade) é uma aresta de custo zero que **não conta** em `max_len`: comprar
dólar numa casa e vender noutra da mesma cidade cabe em `max_len=4`, e levar dinheiro vivo de uma cidade para outra
com troca nas duas pontas também.
`channel`: `presencial` (casa, dinheiro vivo, deslocamento), `assistida` (app de banco), `automatizavel` (nenhuma hoje).
Cotações com `kind: market_reference` ou `modality: reference` (BCP, PTAX) **não** viram aresta: servem só de comparação.
Ciclos simples com até `max_len` pernas (2 a 6, padrão 4) são avaliados com o saldo livre do nó inicial; uma aresta cuja
cotação depende do montante (`amount_base`) só é usada dentro da faixa em que foi cotada. Dinheiro em string decimal (D1).
Várias arestas podem ligar o mesmo par de nós (cartão e espécie, trilho e deslocamento). Todas entram no grafo e a busca
escolhe uma por perna, conforme o montante que chega a ela: só alternativas que aceitam o montante competem, custo
conhecido vence custo desconhecido, e depois vem a maior saída. Por isso um mesmo `path` aparece uma vez só na lista.
Fontes descontinuadas (hoje o ueno, em resolução pelo BCP desde 03/11/2026) não entram no grafo nem na valoração: nem
cotação da fonte, nem cotação com destino nela, nem conta nela. `GET /v1/sources` marca a fonte com `discontinued: true`.

**Custo desconhecido nunca vira zero.** Trilho ausente ou com valor `null`, rota de deslocamento sem `cost`, taxa
de valoração que falta para converter, ou IOF de BRL convertido fora do lado paraguaio (instituição brasileira, fintech,
fonte sem cidade no Paraguai ou casa de FOZ/PPO) sem alíquota conhecida, dá `confidence: "incomplete"` na aresta e no ciclo, e a categoria aparece em `unknown_costs`. Na
perna e no ciclo essa categoria sai `null`, nunca `"0"`. Ciclo `incomplete` não é "lucro confirmado" e nunca dispara
alerta de ganho. Sem taxa de referência, o `spread` da perna de câmbio é `null` (a taxa cotada é o preço total).

**Pernas (`legs[]`)**, uma por aresta, na ordem do ciclo: `kind` (`exchange` (troca, a aresta `quote`) |
`transfer` | `travel` | `deposit` | `withdraw`), `channel`, `from`, `to`, `via`, `minutes`, `border` (cruza BR↔PY),
`amount_in`, `amount_out` e `costs` = `{currency, spread, fees, iof, transport}`, todos na moeda em que a perna
começou; cada custo é `null` quando desconhecido. `spread` é a diferença entre a taxa usada e a taxa de valoração (null sem referência); `fees` tarifas; `iof`
IOF de conversão de BRL por instituição brasileira; `transport` custo de deslocamento.

**Ganhos e avisos do ciclo**: `gain_by_currency` = `{BRL, USD, PYG}` (ganho líquido convertido pelas taxas de
valoração; `null` quando não dá para converter); `costs` = `{spread, fees, iof, transport}` somados na moeda de
partida (`null` se algum custo for desconhecido); `requires_declaration: true` quando uma perna de fronteira move
mais de US$ 10 000 (ou não dá para converter). É um aviso: não bloqueia.

Parâmetros de `GET /v1/opportunities/cycles`: `max_len` (2..6, padrão 4; conta pernas, balcão não conta), `min_roi` (string decimal, ex. `"0.001"`;
sem ele, ciclos com ganho ≤ 0 também aparecem como "quase lá"), `start` (nó de partida, ex. `BRL@nubank`),
`limit` (1..500, padrão 200), `mode` (`celular` padrão, ou `todos`). Ordenação: melhor ROI primeiro.

**Modo celular.** O dono não leva dinheiro em espécie de uma cidade para outra; por isso o ranking principal mostra só o que dá para fazer inteiro pelo celular. No modo `celular`, uma rota ou ciclo só entra se **todas** as pernas forem `assistida` ou `automatizavel`: sai qualquer perna `presencial`, qualquer `travel` (deslocamento), depósito ou saque de espécie e as pernas de balcão. Em `GET /v1/opportunities`, o modo `celular` tira as linhas de canal `physical` da tabela. `mode=todos` devolve o conjunto completo, e a interface o mostra na aba "Presencial (opcional)", com o aviso "exige ir à casa de câmbio". Ciclo sem caminho de volta confirmado continua `confidence: incomplete` ("custo incompleto"), nunca lucro, nos dois modos.

```jsonc
Edge  { "from": "BRL@brbank", "to": "PYG@banco_py", "kind": "quote|transfer|deposit|withdraw|travel", "rate": "1366.5",
        "fee_pct": "0", "fee_fixed": "9.9", "iof_pct": "0", "transport_fixed": "0", "minutes": 240, "via": "wu",
        "confidence": "quoted|estimated|incomplete", "evidence_id": "uuid|null", "channel": "presencial|assistida|automatizavel",
        "border": false, "counter": false, "ref_rate": "1370.2|null", "unknown_costs": ["spread|fees|iof|transport"] }
Leg   { "kind": "exchange|transfer|travel|deposit|withdraw", "channel": "presencial", "from": "PYG@chaco:CDE",
        "to": "USD@chaco:CDE", "via": "chaco cash @CDE (venda 7300)", "minutes": 15, "border": false,
        "amount_in": "7300000", "amount_out": "1000",
        "costs": { "currency": "PYG", "spread": "0", "fees": "0", "iof": "0", "transport": "0" } }
Cycle { "start": "BRL@brbank", "path": ["BRL@brbank","PYG@banco_py","USD@banco_py","BRL@brbank"], "edges": [Edge],
        "legs": [Leg], "amount_in": "25000", "amount_out": "25041.2", "gain": "41.2", "roi": "0.001648",
        "gain_by_currency": { "BRL": "41.2", "USD": "7.6", "PYG": "55000" }, "costs": { "spread": "0", "fees": "9.9",
        "iof": "0", "transport": "0" }, "requires_declaration": false, "minutes": 4320,
        "confidence": "estimated", "data_mode": "real|simulation|demo" }
```

## Planos de execução — módulo `plans` (fase A: sem execução)

Um plano organiza os passos de um ciclo para o dono seguir. **Nada aqui movimenta dinheiro**: nenhuma rota chama banco,
casa ou API. Aprovar grava a decisão; cada passo grava o valor realizado que o dono informou.

```jsonc
PlanOut { "id": "uuid", "status": "proposed|approved|in_progress|done|rejected|expired", "start": "PYG@cash:CDE",
  "path": ["PYG@cash:CDE", "PYG@chaco:CDE", "USD@chaco:CDE", "USD@cash:CDE"], "currency": "PYG",
  "amount_in": "7300000", "amount_out_expected": "7400000", "gain_expected": "100000",
  "gain_by_currency": {"BRL": "70", "USD": "13.7", "PYG": "100000"},
  "costs": {"spread": "0", "fees": null, "iof": "0", "transport": "0"} /* null = custo desconhecido */,
  "confidence": "quoted", "minutes": 55,
  "requires_declaration": false, "quotes_as_of": "2026-11-04T12:00:00Z", "quote_max_age_s": 900,
  "created_at": "...", "decided_at": "...|null", "completed_at": "...|null", "data_mode": "real|simulation|demo",
  "steps": [PlanStepOut] }
PlanStepOut { "n": 1, "kind": "travel", "channel": "presencial", "text": "Leve o dinheiro de CDE para FOZ (≈ 40 min)",
  "from": "BRL@cash:CDE", "to": "BRL@cash:FOZ", "amount_in": "10000", "amount_out_expected": "10000", "minutes": 40,
  "status": "pending|done", "actual_out": "string|null", "note": "string|null", "done_at": "...|null" }
```

- **Ganho com custo pendente** (`confidence: incomplete`) é estimativa: a tela mostra "≈", sem sinal, em tom neutro, com
  o rótulo "não confirmado" e os custos `null` pelo nome. Um ciclo sem ganho positivo não vira plano (`422`).
- **Textos em pt-BR simples**: "Compre 1.000 USD na Cambios Chaco (CDE) pagando 7.300.000 PYG (cotação: 1 USD = 7.300 PYG)",
  "Envie 5.000 BRL de banco brasileiro e receba ≈ 920 USD em Nomad (≈ 60 min)", "Leve o dinheiro de CDE para FOZ
  (≈ 40 min)". A cotação segue a convenção do balcão: 1 unidade da moeda mais forte (USD > BRL > PYG) = quanto da
  mais fraca, sem arredondar o preço para zero. Valores inteiros sem centavos; guarani sem centavos.
- **Estados**: `proposed` → `approved` → `in_progress` → `done`; ou `rejected`; ou `expired`. Um plano que ainda não
  começou expira quando a cotação mais velha dele passa de `quote_max_age_s` (900 s por padrão, `PLAN_QUOTE_MAX_AGE_S`).
  A cotação mais velha é a menor data entre `quoted_at` das arestas de cotação do ciclo e a data da evidência (quando há).
  Um ciclo sem nenhuma data de cotação não vira plano (`422`): nunca se usa "agora" como data da cotação.
  Depois que o primeiro passo é feito, o plano não expira mais.
- **Passos**: em ordem; `409` se pular um passo, repetir um passo já feito ou o plano não estiver aprovado.
- **Resultado**: ao concluir o último passo, o plano grava no diário (`GET /v1/journal`) uma entrada `kind: "result"`
  com `amounts` = `[{label: "esperado", ...}, {label: "realizado", ...}]` e o texto "Plano … concluído: esperado …,
  realizado … (diferença …)".
- **Escritas exigem a chave** de API, como as demais rotas de escrita.

## Alertas — regra de ganho líquido por ciclo

`kind: "cycle_net_gain"`: dispara quando o melhor ciclo tem ganho líquido **positivo** e não menor que `threshold`,
na moeda `params.currency` (`BRL`, `USD` ou `PYG`). `threshold` é um valor absoluto na moeda escolhida (ex. `"20"` = R$ 20),
não um ROI. Só dispara para ciclos com `confidence` `quoted` ou `estimated`; `incomplete` nunca dispara. Usa o cooldown
das demais regras. Os ciclos só são calculados quando existe regra ativa desse tipo.

## Pregão — velas, resumo da sessão e horários das casas (módulo `pregao`)

Não há bolsa nem livro central. Cada casa de câmbio é um formador de mercado independente e publica a própria Compra e Venda pela moeda-base. BCP e dolarPy são referência (`kind: market_reference`): nunca são executáveis, nunca são contraparte, nunca entram nos lados Compra/Venda, nunca são "melhor preço" e nunca são perna de cruzamento. "Últimas atualizações" são cotações publicadas. Não são negócios fechados. Nada neste módulo executa movimentação financeira. Por causa do piso de 60 s por fonte na sondagem, não existe vela abaixo de 15 minutos: os intervalos aceitos são `15m`, `1h`, `4h` e `1d`, e só eles.

### Objetos

```jsonc
Candle {
  "t": "ISO-8601 UTC",                                   // início do bucket
  "o": "decimal", "h": "decimal", "l": "decimal", "c": "decimal",   // string decimal do mid
  "n": 1,                                                // inteiro ≥ 1: cotações com mid no bucket
  "spread_avg": "decimal|null", "buy_c": "decimal|null", "sell_c": "decimal|null",
  "data_mode": "real|simulation|demo"
}
CandleSeries { "key": "string", "tf": "15m|1h|4h|1d", "candles": [Candle], "data_mode": "real|simulation|demo" }
SessionStats {
  "key": "string", "day_start": "ISO-8601 com offset (America/Asuncion)",
  "open": "decimal|null", "high": "decimal|null", "low": "decimal|null", "last": "decimal|null",
  "last_at": "ISO-8601 UTC|null", "change_abs": "decimal|null", "change_pct": "decimal|null",
  "n_quotes": 0, "spread_avg": "decimal|null", "houses": 0,
  "data_mode": "real|simulation|demo"
}
HouseSession {
  "source_id": "string", "name": "string", "city": "CDE|ASU|PJC|FOZ|ENC|null", "tz": "string|null",
  "channel": "physical|digital|null", "reference": false,
  "status": "open|closed|pre|unknown",
  "opens_at": "ISO-8601 UTC|null", "closes_at": "ISO-8601 UTC|null", "next_change_at": "ISO-8601 UTC|null",
  "data_mode": "real|simulation|demo"
}
HouseHours {                                             // entrada de backend/src/fronteira_fx/data/market_hours.json; não é resposta de API
  "name": "string|null", "city": "CDE|ASU|PJC|FOZ|ENC|null", "channel": "physical|digital", "tz": "fuso IANA",
  "days": [1, 2, 3, 4, 5, 6], "opens": "HH:MM", "closes": "HH:MM|24:00",
  "schedule": [{ "days": [7], "opens": "HH:MM", "closes": "HH:MM|24:00" }],  // opcional: janelas de outros dias
  "verified": true, "source_url": "https://...|null", "checked_at": "AAAA-MM-DD"  // opcionais: procedência
}
```

Exemplo de `CandleSeries` para `GET /v1/candles?key=chaco:CDE:USD/PYG:cash&tf=15m&from=2026-11-02T12:00:00Z&to=2026-11-02T12:30:00Z`, com as cotações publicadas às 12:01, 12:06, 12:11 e 12:16 UTC (mid 7335, 7337, 7318 e 7340):

```jsonc
{ "key": "chaco:CDE:USD/PYG:cash", "tf": "15m", "data_mode": "real",
  "candles": [
    { "t": "2026-11-02T12:00:00Z", "o": "7335", "h": "7337", "l": "7318", "c": "7318", "n": 3,
      "spread_avg": "30", "buy_c": "7318", "sell_c": "7352", "data_mode": "real" },
    { "t": "2026-11-02T12:15:00Z", "o": "7340", "h": "7340", "l": "7340", "c": "7340", "n": 1,
      "spread_avg": "30", "buy_c": "7325", "sell_c": "7355", "data_mode": "real" }
  ] }
```

No bucket `12:00Z` entram as cotações de 12:01, 12:06 e 12:11 (a de 12:11 só tem Compra, por isso não altera `spread_avg` nem `sell_c`). A de 12:16 cai no bucket `12:15Z`. Com `tf = 1h`, as quatro cotações formam um único bucket `12:00Z`: `o "7335"`, `h "7340"`, `l "7318"`, `c "7340"`, `n 4`, `spread_avg "30"`, `buy_c "7325"`, `sell_c "7355"`.

Exemplo de `SessionStats` para `GET /v1/pregao/stats?keys=chaco:CDE:USD/PYG:cash`, com `now` = 12:30Z e as mesmas quatro cotações (só `chaco` publica esse par na janela, por isso `houses` é 1):

```jsonc
{ "key": "chaco:CDE:USD/PYG:cash", "day_start": "2026-11-02T00:00:00-03:00",
  "open": "7335", "high": "7340", "low": "7318", "last": "7340", "last_at": "2026-11-02T12:16:00Z",
  "change_abs": "5", "change_pct": "0.06816633", "n_quotes": 4, "spread_avg": "30", "houses": 1,
  "data_mode": "real" }
```

Exemplo de `HouseSession` para `GET /v1/pregao/sessions` (segunda-feira, 12:00Z, que é 09:00 em Assunção):

```jsonc
{ "source_id": "chaco", "name": "Cambios Chaco", "city": "CDE", "tz": "America/Asuncion",
  "channel": "physical", "reference": false, "status": "open",
  "opens_at": "2026-11-02T10:30:00Z", "closes_at": "2026-11-02T20:00:00Z", "next_change_at": "2026-11-02T20:00:00Z",
  "data_mode": "real" }
```

### Velas — `GET /v1/candles`

- Parâmetros: `key` (obrigatório, chave de série), `tf` (`15m`, `1h`, `4h` ou `1d`), `from` e `to` (ISO-8601; sem fuso, são UTC) e `limit` (padrão 300, mínimo 1, máximo 1000). No Python os parâmetros se chamam `start` e `end`, por `alias`.
- `from` é inclusivo e `to` é exclusivo, sobre `captured_at`. Padrões: `to` = agora (UTC); `from` = `último − (limit − 1) · grid_s`, em que `último` é o bucket corrente (`bucket_start(agora)`) sem `to` e, com `to` informado, o bucket do instante logo antes de `to` (`bucket_start(to − 1 µs)`): com `to` numa fronteira (ex.: `12:00Z` em `1h`), o bucket que começa em `to` não entra e a janela ainda comporta `limit` buckets. Com `from` informado, a janela começa em `from_eff = bucket_start(from)`.
- Corte pela cauda: se a janela tiver mais buckets que `limit`, a resposta traz as últimas `limit` velas, em sequência crescente. O servidor lê as cotações de trás para frente e para ao completar `limit` buckets, então um `from` antigo não custa mais que a resposta.
- `from` e `to` precisam ficar entre `1970-01-01T00:00:00Z` (inclusivo) e `2100-01-01T00:00:00Z` (exclusivo), já convertidos para UTC; fora disso, `422` com `detail` `"from: data fora do intervalo aceito (de 1970-01-01 a 2099-12-31 UTC)"` (ou `"to: …"`).
- `from` igual ou posterior a `to` → `422` com `{"detail": "from deve ser anterior a to"}`.
- Sem cotações na janela → `200` com `"candles": []`, nunca 404.
- Valores fora de `tf` ou `limit`, e datas malformadas, são validados pelo FastAPI (422 padrão, com `detail` em lista).
- Chave de série: `{source_id}:{city|digital}:{base}/{quote}:{modality}[:@{branch_id}][:{amount}][:{ctx8}]`, com 3 a 255 caracteres e os quatro primeiros segmentos obrigatórios (`^[^:,]+:[^:,]+:[A-Z]{3}/[A-Z]{3}:[^:,]+(:[^,]+)?$`); fora disso, `422` padrão do FastAPI. Sem o par, um prefixo como `chaco` juntaria USD/PYG e BRL/PYG na mesma vela. O casamento é por prefixo: `chaco:CDE:USD/PYG:cash` casa com ela mesma e com `chaco:CDE:USD/PYG:cash:@chaco-cde-centro`, mas não com `chaco:CDE:USD/PYG:cash_promo`. Toda consulta filtra `Quote.data_mode == mode`.
- `mid = (buy + sell) / 2` quando os dois lados existem; o lado presente quando só um existe; cotação sem nenhum lado é ignorada.
- Buckets alinhados ao epoch Unix em UTC (o dia começa às 00:00Z): `bucket_start(ts) = epoch(ts) − epoch(ts) mod grid_s`, com `grid_s` = 900 (`15m`), 3600 (`1h`), 14400 (`4h`) e 86400 (`1d`). Uma cotação pertence ao bucket `B` quando `B ≤ captured_at < B + grid_s`.
- Buckets vazios não são emitidos: sem preenchimento e sem repetir o último `c`. A sequência sai crescente por `t`, sem `t` repetido.
- Campos por bucket: `o` é o primeiro mid, `c` o último, `h` o máximo e `l` o mínimo; `n` conta as cotações com mid; `spread_avg` é a média de `sell − buy` nas cotações com os dois lados (`null` se nenhuma), com sinal: negativo indica livro cruzado (Compra acima da Venda); `buy_c` e `sell_c` são o último buy e o último sell não nulos (`null` se nenhum). Os três campos nulos são sempre emitidos, nunca omitidos.
- Sem arredondamento na agregação. Na saída, os decimais têm até 8 casas, com arredondamento ROUND_HALF_EVEN e sem zeros à direita (`"7335"`, não `"7335.00000000"`).

### Resumo da sessão — `GET /v1/pregao/stats`

- `keys`: chaves separadas por vírgula, num único parâmetro. Espaços em volta são removidos e entradas vazias descartadas. São aceitas de 1 a 20 chaves; fora disso, `422` com `{"detail": "keys: informe de 1 a 20 chaves"}`. Cada chave segue o mesmo formato de `/v1/candles` (quatro segmentos, até 255 caracteres); uma chave fora dele dá `422` com `detail` começando por `"keys: chave inválida"` e a chave (truncada em 60 caracteres). O parâmetro inteiro tem no máximo 5120 caracteres. A resposta traz uma `SessionStats` por chave, na mesma sequência pedida.
- `now` é o instante da requisição, em UTC.
- `day_start`: 00:00 local em `America/Asuncion` do dia que contém `now`, com offset (ex.: `2026-11-02T00:00:00-03:00`). Exemplo: 02:30Z de 2 de novembro ainda é 1 de novembro em Assunção, então `day_start` é `2026-11-01T00:00:00-03:00`. A consulta usa esse instante convertido para UTC.
- Janela: `day_start ≤ captured_at ≤ now`, considerando só cotações com mid não nulo.
- `open`, `high`, `low` e `last` são o primeiro, o máximo, o mínimo e o último mid da janela; `last_at` é o `captured_at` do último.
- `change_abs = last − open`. `change_pct = (last − open) / open · 100`, em string já multiplicada por 100; é `null` se `open` for nulo ou zero.
- `n_quotes` conta as cotações com mid na janela. `spread_avg` é a média de `sell − buy` nas cotações com os dois lados (diferença na moeda de cotação, não percentual, com sinal: negativo indica livro cruzado, Compra acima da Venda).
- `houses` conta as casas distintas (`source_id`) com cotação do mesmo par (segmento `[2]` da chave), no mesmo `data_mode` e na mesma janela, em qualquer cidade e modalidade. Cotações com `kind: market_reference` ficam de fora.
- Sem cotações na janela: os campos decimais e `last_at` são `null`; `n_quotes` é `0`; `houses` é `0`.

### Horários das casas — `GET /v1/pregao/sessions`

- Arquivo: `backend/src/fronteira_fx/data/market_hours.json`, com chaves iguais ao `source_id` sem o prefixo `demo-`. Há um horário por fonte, com os campos de `HouseHours`. `days` usa dias ISO (1 = segunda … 7 = domingo); lista vazia significa sempre fechada. `opens` e `closes` são `HH:MM`, e `closes` aceita `24:00`.
- `schedule` (opcional) dá janela própria a outros dias, por exemplo sábado mais curto ou domingo com horário. Os dias de `schedule` não podem repetir `days` nem outra janela, senão é erro ao carregar. Dia fora de `days` e de `schedule` é fechado. Ex.: `days: [1..5]` com `08:30–17:00` e `schedule: [{days: [6], 09:00–12:00}]` abre sábado até 12:00 e fecha domingo.
- Campos de procedência, opcionais e ignorados pelo status: `verified` (`true` só com horário confirmado ou corrigido na checagem), `source_url` e `checked_at` (data da checagem). Casa sem horário verificado não entra no arquivo: aparece como `unknown`.
- `closes ≤ opens` é erro ao carregar o arquivo, com o `source_id` na mensagem: não existe horário que atravesse a meia-noite. Fonte sem horário cadastrado → `unknown`.
- `PRE_OPEN_MIN = 30`: a pré-abertura são os 30 minutos antes de `opens`.
- Rótulos da tela: `open` = "aberta", `closed` = "fechada", `pre` = "pré-abertura", `unknown` = "sem horário".
- Algoritmo do `status` (`now` em UTC; `opens_at`, `closes_at` e `next_change_at` saem em UTC):
  1. Sem horário ou com `tz` inválido → `unknown`, com os três campos de horário `null`.
  2. Sete dias e `00:00`–`24:00` (casa digital sempre aberta) → `open`, com os três campos `null`.
  3. `now` é convertido para o fuso da casa; daí saem o dia da semana e o minuto do dia local.
  4. Dia de funcionamento (janela de `days` ou de `schedule`) e `opens ≤ agora < closes` → `open`; `opens_at` e `closes_at` são de hoje; `next_change_at = closes_at`.
  5. Dia de funcionamento e até 30 minutos antes de `opens` → `pre`; `opens_at` e `closes_at` são de hoje; `next_change_at = opens_at`.
  6. Nos demais casos → `closed`. Procura-se o próximo dia de funcionamento (com a janela desse dia), começando por hoje se a pré-abertura de hoje ainda não começou, senão por amanhã, até 8 dias à frente. Encontrado, `opens_at` e `closes_at` são desse dia e `next_change_at = opens_at − 30 min`. Não encontrado (ex.: `days` vazio) → `closed` com os três campos `null`.
  7. Horário local vira UTC pelo fuso da casa; `24:00` é 00:00 do dia seguinte.
- `name` vem de `HouseHours.name`; sem ele, usa `Source.name` e, na falta deste, o `source_id`.
- `reference: true` para fontes `central_bank` (BCP) e para as que declaram a capacidade `reference_only` ou `market_reference` (dolarPy, `kind: fintech`). Referências aparecem na resposta, mas o resumo da tela as deixa fora do total e das casas abertas.

### Modos de dados

- Todo objeto leva `data_mode`, com `real`, `simulation` ou `demo`.
- `real` e `simulation` consultam o banco filtrando por `Quote.data_mode` (e as fontes por `Source.data_mode`).
- `demo` não toca o banco: as três rotas usam geradores determinísticos no servidor. O cliente tem o mesmo gerador para a faixa de demonstração, então os valores batem.

### Compatibilidade

- Enquanto o router `pregao` não estiver publicado em um ambiente, o frontend recorre a `GET /v1/history?key=&grid=300` e agrega localmente com as mesmas regras; nessa aproximação `n` conta pontos de 5 min com `mid`, não cotações.
- `404` em `/v1/candles` ativa esse recurso. `404` em `/v1/pregao/stats` ou `/v1/pregao/sessions` vira lista vazia no cliente.

### Percentuais

- A API devolve percentuais como string já multiplicada por 100: `"0.06816633"` representa 0,07 %. O cliente formata com `formatPercent(v / 100)`.

## Instituições — `GET /v1/institutions`

Cadastro versionado em `backend/src/fronteira_fx/data/institutions.json` (loader validado em `services/institutions.py`).
Não depende de `data_mode`: é o mesmo em qualquer instância. Operação MCP: `list_institutions`.

`Institution`: `id`, `name`, `country` (`BR` | `PY` | `INT`: país em que o titular abre a conta), `kind` (`bank` | `fintech` | `wallet` | `broker`),
`status` (`active` | `discontinued`, com `discontinued_note`), `currencies_held` (lista ou `null`), `opens_remotely` (bool ou `null`),
`requires` (texto ou `null`), `api` (`none` | `pf` | `pj_contract` ou `null`), `api_source_url`, `source_url`, `checked_at` (data `YYYY-MM-DD`),
`fx_cost: {spread_pct, iof_pct, fee_pct, fee_fixed}`.

Regras de proveniência:

- Cada `Figure` tem `value` (string decimal ou `null`), `currency` (obrigatória em `fee_fixed` quando há valor), `source_url`, `checked_at` e `note`.
  Percentuais são frações (`"0.035"` = 3,5 %). Valor `null` = não confirmado pela pesquisa, nunca zero.
- Fato não nulo exige fonte: `currencies_held`, `opens_remotely` e `requires` usam `source_url` + `checked_at` da entrada; `api` usa `api_source_url`.
- `checked_at` é a data da verificação registrada na pesquisa de 04/11/2026; não é uma nova consulta aos sites.
- `ueno` está `discontinued` (resolução do BCP). Nenhuma instituição entra no cálculo de lucro sem a figura confirmada.

## Regras do ranking

1. Digital com `net_gain > 0` (após custos conhecidos) entra no ranking principal, mesmo microganho.
2. Físico entra no principal apenas se `roi_fisico >= melhor_roi_digital_comparavel + 0.01` (mesmo capital, objetivo, prazo).
3. `confidence = incomplete` quando falta custo essencial → exibido como estimativa incompleta, nunca como lucro confirmado.

## MCP

Servidor em `/mcp` (mesma chave de API, quando definida). As 18 ferramentas têm o mesmo nome do `operationId`
da rota que espelham e nunca passam por outro caminho:

- núcleo: `list_sources`, `get_quotes`, `request_quote`, `get_history`, `compare_routes`, `simulate_cycle`, `find_cycles`, `search_evidence`
- watch: `watch_status`, `list_changes`, `trigger_poll`
- notify: `list_alert_rules`, `create_alert_rule`
- rag: `search_knowledge`
- memory: `remember`, `recall`, `forget`, `memory_summary`

## Monitoramento ao vivo (sites sem API) — módulo `watch`

Sites sem API não "empurram" dados; o máximo possível é **sondagem inteligente**: requisições condicionais (ETag /
If-Modified-Since), hash do conteúdo relevante para detectar mudança real, intervalo adaptativo (mais curto quando a
fonte muda com frequência ou em horário comercial; recuo exponencial após erros/bloqueio), respeito a limites, e
emissão de evento no stream assim que algo muda.

| Método | Rota | Descrição |
|---|---|---|
| GET | `/v1/watch/sources` | `WatchStatus[]` |
| POST **[chave]** | `/v1/watch/sources/{id}` | body `{interval_s?, enabled?}` — ajuste manual (`interval_s` respeita `min_interval_s`/`max_interval_s`) |
| POST **[chave]** | `/v1/watch/run/{id}` | sondagem imediata. `200` → `Change | null` (`null` = sondou e nada mudou); `404` fonte sem adaptador; `409` instância fora do modo `real` (`simulation`/`demo` nunca consultam provedores); `429` + header `Retry-After` (segundos) se a fonte foi sondada há menos de 60 s |
| GET | `/v1/watch/changes?source=&from=&kind=&limit=200` | `Change[]` (`limit` 1..1000) |

```jsonc
WatchStatus { "source_id": "chaco", "enabled": true, "interval_s": 120, "min_interval_s": 60, "max_interval_s": 900,
  "next_run_at": "...", "last_run_at": "...", "last_change_at": "...|null", "changes_24h": 7, "errors_in_row": 0,
  "etag": "string|null", "last_modified": "string|null",   // ecoados como If-None-Match / If-Modified-Since (GET condicional)
  "content_hash": "sha256|null", "status": "ok|degraded|blocked|stale|error|needs_session" }
Change { "id": "uuid", "source_id": "chaco", "ts": "...", "kind": "quote_change|layout_change|status_change",
  "summary": "USD/PYG CDE venda 7350 → 7360",   // texto para humanos; regras de alerta nunca o analisam
  "before": QuoteSnapshot | {}, "after": QuoteSnapshot | {}, "evidence_id": "uuid|null" }
QuoteSnapshot {                                  // `before`/`after` de um `quote_change` (before = {} quando a cotação é nova)
  "buy": "7290|null", "sell": "7360|null", "captured_at": "...", "series_key": "chaco:CDE:USD/PYG:cash",
  "quote_id": "uuid", "pair": "USD/PYG", "city": "CDE|null", "source_id": "chaco",
  "modality": "cash", "channel": "physical" }       // modality/channel: ausentes em linhas gravadas antes desta versão
```
Eventos no stream: `source.change` (payload `Change`) e `alert.fired` (payload `AlertEvent`).
MCP: `watch_status`, `list_changes`, `trigger_poll`.

## Alertas / notificações — módulo `notify`

| Método | Rota | Descrição |
|---|---|---|
| GET/POST **[chave]** | `/v1/alerts/rules` | `AlertRule[]` / cria (POST exige chave) |
| PATCH/DELETE **[chave]** | `/v1/alerts/rules/{id}` | atualiza / remove |
| GET | `/v1/alerts/events?from=&rule=&limit=200` | `AlertEvent[]` (`limit` 1..1000) |
| POST **[chave]** | `/v1/alerts/test/{id}` | envia mensagem de teste pelo canal da regra |

```jsonc
AlertRule { "id": "uuid", "name": "ciclo > 0,2 %", "kind": "cycle_roi|quote_move|source_down|opportunity_new|cycle_net_gain",
  //   cycle_net_gain: params {"currency": "BRL|USD|PYG"} obrigatório; threshold = ganho líquido mínimo naquela moeda
  "threshold": "0.002", "params": { "pair": "USD/PYG", "city": "CDE|digital|null" } | null,   // quote_move compara com Change.after.pair/city;
  //   city "digital" = só cotações sem cidade; ausente/null = qualquer cidade; referências (modality=reference ou
  //   channel=aggregator, ex. dolarPy) nunca disparam quote_move
  "channel": "ui|telegram|webhook|email", "target": "chat_id|url|email|null", "cooldown_s": 600, "enabled": true,
  "last_fired_at": "...|null" }
AlertEvent { "id": "uuid", "rule_id": "uuid", "ts": "...", "message": "...", "payload": {}, "channel": "telegram",
  "delivered": true, "error": "string|null" }
```
Segredos (token do bot, SMTP) só por variáveis de ambiente do backend. MCP: `list_alert_rules`, `create_alert_rule`.

## Mercado: notícias, referências e volatilidade — módulo `market`

Notícias de feeds públicos, referências de mercado (cripto, câmbio de referência, séries do BCB) e volatilidade.
**Tudo aqui é referência de mercado: `executable` é sempre `false`, nunca é preço de casa de câmbio e nunca entra
no grafo de posições nem no motor de ciclos.** Só o worker consulta provedores (piso de 60 s por fonte); a API só lê.
Em `demo` os dados são semeados e marcados `demo` (manchetes ilustrativas, links `.invalid`); em `simulation` não há dados.

| Método | Rota | Descrição |
|---|---|---|
| GET | `/v1/market/news?source=&since=&limit=50` | `NewsItem[]`, mais recente primeiro (1..200). `source`: `infomoney`, `agencia-brasil`, `bcb`, `mercopress`, `demo` |
| GET | `/v1/market/quotes` | `MarketQuote[]`, uma linha por instrumento (última referência) |
| GET | `/v1/market/volatility` | `MarketVolatility[]`, um por instrumento cripto (BTC/USDT, ETH/USDT, USDT/BRL) |

```jsonc
NewsItem { "id": "uuid", "source": "infomoney", "feed": "infomoney-economia", "title": "string (≤300)", "link": "https://...",
  "published_at": "...|null", "captured_at": "...", "data_mode": "real" }
MarketQuote { "instrument": "USD/PYG", "label": "USD/PYG (guarani, via Frankfurter)", "kind": "crypto|fx_reference|bcb_series",
  "source": "binance|frankfurter|bcb", "price": "5958", "change_pct": "0.12|null", "observed_at": "...", "captured_at": "...",
  "executable": false, "note": "Referência de mercado. Não é preço executável nem cotação de casa de câmbio.", "data_mode": "real" }
MarketVolatility { "instrument": "USDT/BRL", "status": "ok|insufficient_data|stale_input", "as_of": "...|null",
  "last_close": "5.5179|null", "last_move_pct": "0.12|null", "ewma_pct_5m": "0.08|null", "parkinson_1d_pct": "...|null",
  "parkinson_20d_pct": "...|null", "ratio_1d_20d": "...|null", "atr_14_5m": "...|null (em preço)",
  "regime": "normal|alta|muito_alta|null", "alert": false, "reasons": ["movimento_acima_de_3x_ewma"], "data_mode": "real" }
```
Percentuais em `%`, valores em string decimal. `status` diferente de `ok` → `regime` e `alert` nulos/falsos (nunca um número inventado).
Eventos no stream: `market.news` (uma por manchete nova) e `market.volatility_alert` (na transição para alerta).
MCP: `list_market_news`, `get_market_quotes`, `get_market_volatility`.

## RAG (documentação, tarifas, horários, evidências) — módulo `rag`

| Método | Rota | Descrição |
|---|---|---|
| POST **[chave]** | `/v1/rag/documents` | body `{title, text, source, tags[], metadata?}` → `{id, chunks}` |
| GET | `/v1/rag/search?q=&k=5&tag=` | `[{id, document_id, title, snippet, score, source, tags}]` (`k` 1..50; busca léxica) |
| GET | `/v1/rag/documents` | `[{id, title, source, tags, chunks, created_at}]` |

Cotações e cálculos **nunca** vêm do RAG: vêm do banco e do motor. MCP: `search_knowledge`.
A base `backend/knowledge/*.md` (front matter `title`/`source`/`tags`) é semeada no startup, de forma idempotente
(um documento por arquivo, hash sha256 em `metadata`), no `data_mode` da instância; `SEED_KNOWLEDGE=false` desliga e
`python -m fronteira_fx.cli seed-knowledge` faz o mesmo sob demanda.

## Memória do agente — módulo `memory`

| Método | Rota | Descrição |
|---|---|---|
| POST **[chave]** | `/v1/memory` | body `{kind: "preference|decision|fact|outcome", text, tags[], ttl_days?, source?:"user|agent"}` → `Memory` (201) |
| GET | `/v1/memory?q=&kind=&tag=&limit=20` | `Memory[]` (mais recentes primeiro, só não expiradas). `q` é substring literal, sem distinção de caixa (`%`/`_` não são curingas); `tag` casa a tag inteira; `limit` 1..100, padrão 20 (ver `docs/memoria.md`) |
| GET | `/v1/memory/summary?limit=5` | `{summary}` — uma linha por tipo (`Preferências`, `Decisões`, `Fatos`, `Resultados`), itens mais recentes primeiro, até `limit` (1..100) por tipo, cada item com até 200 caracteres (`…`); `""` sem memórias |
| DELETE **[chave]** | `/v1/memory/{id}` | remove (204; 404 se não existir no `data_mode` da instância) |

```jsonc
Memory { "id": "uuid", "kind": "decision", "text": "...", "tags": ["ueno"], "created_at": "...", "expires_at": "...|null", "source": "user|agent" }
MemorySummary { "summary": "Preferências: prefere Pix para receber\nFatos: ueno cobra IOF; …" }
```
MCP: `remember`, `recall`, `forget`, `memory_summary`.

## Coleta disparada de fora — módulo `internal` (modo serverless)

Uso: o agendador (no Supabase, `pg_cron` + `pg_net`, ver `docs/deploy.md`) chama a rota a cada 5 minutos. Não é
para o frontend. Cada chamada faz **uma volta** do laço do worker, sem processo residente:

- fontes vencidas pelo agendamento e pelo recuo já existentes (nunca forçadas; piso de 60 s por fonte);
- tarefas da fila de cotação sob demanda, exceto as de fontes com navegador (ficam `queued` para o worker);
- limpeza do stream de eventos;
- fontes de método `browser` são puladas com motivo: não há navegador nesse modo;
- nenhuma fonte nova (nem tarefa) começa depois de `COLLECT_BUDGET_S` (padrão 45 s; a função tem 60 s).

| Método | Rota | Autenticação | Respostas |
|---|---|---|---|
| POST | `/v1/internal/collect` | `Authorization: Bearer <CRON_SECRET>` | `200` rodada; `400` lista `sources` inválida; `401` segredo ausente ou errado; `404` `CRON_SECRET` não definido |

**Corpo opcional `{"sources": ["chaco", "alberdi"]}`** (`CollectRequest`, sem campos extras). Sem corpo ou com `{}`,
vale a rodada normal acima. Com a lista, a rota faz só o seguinte:

- coleta **só** as fontes listadas, com agendamento **forçado** (não espera o `next_poll_at`);
- o piso de 60 s por fonte continua valendo: uma fonte sondada há menos de 60 s entra em `skipped` com o motivo
  "sondada há pouco; piso de 60 s";
- fontes de método `browser` entram em `skipped` ("requer navegador") sem mini navegador configurado;
- ids repetidos são colapsados; até 30 ids por chamada (mais que isso: `400`);
- id desconhecido: `400` com `"fonte desconhecida na lista `sources`"`. O valor enviado **não** volta na resposta
  e nenhuma fonte é consultada;
- não processa a fila de tarefas nem limpa eventos (isso fica na rodada normal);
- a resposta tem o mesmo formato `CollectRoundOut`; `tasks_processed` e `events_pruned` valem `0`.

Quem chama: o vigia do Supabase (`fronteira-fx/deploy/supabase/vigia.sql`), só quando uma fonte mudou.

Resposta `200` (`CollectRoundOut`):

```jsonc
{
  "duration_ms": 1832,
  "data_mode": "real",
  "budget_s": 45.0,
  "budget_exhausted": false,
  "sources": [ { "id": "chaco", "status": "ok", "health": "ok", "changed": true, "quotes_stored": 4 } ],
  "skipped": [ { "id": "wu", "reason": "requer navegador; só o worker coleta essa fonte" } ],
  "tasks_processed": 0,
  "events_pruned": 0
}
```

- `changed` é `true` quando uma cotação mudou em relação à captura anterior (captura nova).
- `skipped[].reason` é texto do servidor, nunca mensagem de provedor. A resposta não traz segredo, cabeçalho
  nem corpo de terceiros.
- Fora do modo `real` a rodada não consulta provedores: `sources` e `skipped` vêm vazios.

## Conexões de conta — módulo `connections`

Regras que este módulo não quebra: nenhuma senha de banco entra, sai ou fica guardada; nada executa ordem, saque ou
transferência; segredo só no backend por `FX_CONNECTIONS_KEY`; respostas nunca trazem chave, segredo nem cabeçalho de
autenticação; dinheiro trafega como string decimal.

- Todas as rotas exigem `X-API-Key` (ou Bearer). Sem `API_KEY` configurada a rota responde `503` ("exige API_KEY"),
  porque o cofre guarda chave de corretora.
- Sem `FX_CONNECTIONS_KEY` o cofre fica desligado: qualquer rota que cifra, decifra ou valida chave responde `503`.
  Listar e apagar continuam funcionando. Chave malformada (não são 32 bytes em base64) também responde `503`.
- `422` de validação de corpo nunca devolve o valor enviado (`input` é removido nas rotas de conexões).

Objeto `Connection`:

```jsonc
{
  "id": "uuid",
  "institution": "binance",          // slug minúsculo
  "label": "Binance leitura",
  "kind": "consent|readonly_key|statement|manual",
  "status": "pending|active|error",
  "data_mode": "real",
  "account_id": "uuid|null",          // conta manual vinculada (opcional)
  "key_hint": "wxyz|null",            // só os 4 últimos caracteres da chave pública
  "balances": [ { "asset": "USDT", "free": "120.5", "locked": "0" } ],   // snapshot da última leitura, sem segredo
  "last_error": "string|null",        // resumo curto, sem segredo
  "last_synced_at": "2026-11-04T12:00:00Z|null",
  "created_at": "...", "updated_at": "..."
}
```

| Método | Rota | Descrição |
|---|---|---|
| GET **[chave]** | `/v1/connections` | `Connection[]` do modo da instância |
| POST **[chave]** | `/v1/connections` | cria. `kind=readonly_key` exige `api_key` e `api_secret`: valida na corretora antes de cifrar e gravar. `201 Connection`; `422` se a chave for recusada (motivos em `detail`); `503` sem cofre. `kind=statement` aceita `account_id`. `kind=manual` só registra. `kind=consent` → `422` (usa a rota de consentimento) |
| POST **[chave]** | `/v1/connections/validate-key` | body `{institution, api_key, api_secret}` → `KeyCheck`. Não grava nada. `200` mesmo quando recusa: `ok:false` com `reasons`. `503` sem cofre |
| POST **[chave]** | `/v1/connections/{id}/sync` | só `readonly_key`. Decifra a chave guardada, confere as permissões de novo e relê saldos. Chave que passou a ter permissão de operar ou sacar vira `status:"error"` com `last_error`. `503` se o cofre não decifra |
| POST **[chave]** | `/v1/connections/{id}/statement` | só `kind=statement`. body `{format:"csv"|"ofx", content, mapping?, default_currency?}` → `StatementImportOut` |
| POST **[chave]** | `/v1/connections/openfinance/consent` | consentimento Open Finance. Sem provedor: `503 "Open Finance não configurado …"` (explica que é preciso contratar um agregador). Provedor configurado sem integração nesta versão: `501`. Nunca recebe credencial de banco |
| DELETE **[chave]** | `/v1/connections/{id}` | `204`. Apaga a conexão, o ciphertext e os lançamentos importados. A conta vinculada não muda |

`KeyCheck`: `{ "ok": bool, "institution": "binance", "flags": {"enableWithdrawals": false, ...}, "reasons": [], "balances": [Balance] }`.

### Validação de chave só leitura

- **Binance** (`GET /sapi/v1/account/apiRestrictions`, assinado HMAC-SHA256, header `X-MBX-APIKEY`): recusa se
  `enableSpotAndMarginTrading`, `enableMargin`, `enableFutures`, `enableWithdrawals`, `enableInternalTransfer`,
  `permitsUniversalTransfer`, `enableVanillaOptions` ou `enablePortfolioMarginTrading` não estiver explicitamente `false`
  (ausente conta como ligado). Exige `enableReading: true`. Depois lê `GET /api/v3/account` e recusa se `canTrade` ou
  `canWithdraw` não forem `false`. Saldos vêm desse endpoint; nenhum endpoint de ordem é chamado.
- **Kraken**: recusada por padrão. A API não expõe permissões da chave; a mensagem explica como criar uma chave só com
  "Query Funds".
- **Outras instituições**: recusadas por padrão, sem validação nesta versão.

### Importação de extrato

- Limite: 512 KiB de texto e 5000 lançamentos. Acima disso, `422`.
- **CSV**: `mapping` obrigatório com `date`, `description`, `amount` (nomes das colunas) e `currency` opcional
  (senão `default_currency`). `date_format` ∈ `%Y-%m-%d`, `%d/%m/%Y`, `%d-%m-%Y`, `%Y/%m/%d`, `%d.%m.%Y`. `delimiter` ∈ `,` `;` `TAB`.
  Valores aceitos: `1234.56`, `1.234,56`, `1,234.56`, `-12,5`, `(12,50)`.
- **OFX** 1.x/2.x: lido como texto (`CURDEF`, `STMTTRN`, `DTPOSTED`, `TRNAMT`, `FITID`, `NAME`/`MEMO`). Nenhuma entidade
  externa é resolvida e nada do arquivo é executado.
- Erro em qualquer linha recusa o arquivo inteiro: `422` com `detail` = lista de `linha N: …` (máx. 20).
- Reimportar o mesmo arquivo não duplica: `duplicates` conta o que já existia (FITID quando há; senão data+valor+moeda+descrição+ordem).
- Com `account_id`, o saldo livre da conta manual recebe a soma dos lançamentos novos (`balance_delta`). Moeda diferente
  da conta → `422` e nada é gravado.

`StatementImportOut`: `{connection_id, format, imported, duplicates, account_id, balance_delta, account_balance_free}`.

### Modos de dados

Conexões têm `data_mode` como o resto: a instância só enxerga as suas. `?data_mode=` diferente → `409`.

### Decisões de tela (conexões)

- **Segredo da API** é o único campo `type="password"` da tela de conexões (o login é outro campo, fora deste módulo).
  Motivo: a máscara por CSS (`-webkit-text-security`) não é garantida em todos os navegadores, e o segredo não pode
  ficar legível. `autocomplete="off"` e marcadores de gerenciador de senha (`data-lpignore`, `data-1p-ignore`,
  `data-bwignore`) impedem o cofre de senhas de guardar o segredo. A chave pública segue em texto mascarado por CSS.
  Nenhum campo de senha de banco existe; o teste e2e confere o campo.
- **Extrato CSV** exige o mapeamento de colunas (`mapping`, obrigatório para CSV); a tela envia o conteúdo em JSON
  para `POST /v1/connections/{id}/statement` e apaga a conexão recém-criada se o envio falhar.
- **Agregador de Open Finance** ainda não aparece em `GET /v1/connections`: a tela trata como não configurado
  (botão desabilitado). `POST /v1/connections/openfinance/consent` ainda não tem resposta de sucesso definida no
  backend (o openapi diz `ConnectionOut`, sem `redirect_url`); a tela só redireciona quando receber `redirect_url` https.
- **Contrato testado**: `src/test/connections-openapi.test.ts` confere campos de resposta, corpos enviados e rotas
  contra `src/test/fixtures/connections-openapi.json` (subconjunto do openapi exportado em 3138bbd). Mudou o backend →
  atualizar o fixture e os schemas no mesmo commit.
