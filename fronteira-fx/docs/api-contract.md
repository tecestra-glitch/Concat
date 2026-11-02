# Fronteira FX — contrato da API v1 (fonte da verdade compartilhada)

Frontend (Next.js) e backend (FastAPI) implementam exatamente estes formatos.
Todos os valores monetários trafegam como **string decimal** (ex.: `"7312.50"`) para preservar precisão;
o frontend converte só na exibição. Datas em ISO-8601 UTC.

## Enumerações

- `Currency`: `BRL | USD | PYG`
- `City`: `CDE` (Ciudad del Este) | `ASU` (Asunción) | `PJC` (Pedro Juan Caballero) | `null` (operação digital, sem cidade)
- `Channel`: `digital | physical`
- `Modality`: `cash | transfer | account | card_debit | card_credit | card_virtual`
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
  "method": "html", "url": "https://...", "health": "ok", "last_success_at": "...|null", "last_error": "string|null",
  "capabilities": ["branch_table","buy_sell","usd_pyg","brl_pyg"],
  "limitations": ["sem API oficial", "cotação por filial requer navegador"],
  "coverage": { "cities": ["CDE","ASU"], "currencies": ["USD","BRL","PYG"] },
  "poll_interval_s": 300, "data_mode": "real|simulation|demo"
}
Branch { "id": "chaco-cde-centro", "source_id": "chaco", "name": "...", "city": "CDE", "address": "string|null" }
Quote {
  "id": "uuid", "source_id": "chaco", "branch_id": "chaco-cde-centro|null", "city": "CDE|null",
  "base": "USD", "quote": "PYG",            // preço de 1 base em quote
  "buy": "7300", "sell": "7450",            // string decimal ou null; na perspectiva da casa (compra = ela compra base)
  "unit_note": "PYG por 1 USD",
  "amount_base": "5000|null",               // montante usado quando a cotação depende do valor
  "modality": "cash", "kind": "indicative", "channel": "physical|digital",
  "context": { "payment": "pix", "receive": "bank_account", "bank": null, "promo": "fee_100_off" } | null,
  "fees": [{ "label": "tarifa", "amount": "0", "currency": "BRL" }],
  "captured_at": "...", "declared_updated_at": "...|null", "valid_until": "...|null",
  "evidence_id": "uuid", "data_mode": "real|simulation|demo"
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
Evidence { "id": "uuid", "source_id": "chaco", "kind": "html|screenshot|json|manual", "url": "...", "captured_at": "...", "sha256": "...", "excerpt": "string", "rules": ["parser chaco v1"] }
JournalEntry { "id": "uuid", "ts": "...", "kind": "note|operation|reconciliation", "text": "...", "amounts": [Fee], "account_ids": [] }
StreamEvent { "id": "123", "type": "quote.updated|source.health|opportunity.updated|heartbeat", "ts": "...", "payload": {} }
```

## Endpoints

| Método | Rota | Descrição |
|---|---|---|
| GET | `/v1/health` | `{status, data_mode, db, version}` |
| GET | `/v1/sources` | `Source[]` |
| GET | `/v1/sources/{id}/branches` | `Branch[]` |
| GET | `/v1/quotes?city=&base=&quote=&source=&modality=&amount=` | `Quote[]` (mais recente por contexto) |
| POST | `/v1/quotes/request` | body `{source_id, params}` → `{status:"done"|"queued"|"blocked", quote?, job_id?, reason?}` |
| GET | `/v1/history?key=&from=&to=&grid=300` | `HistorySeries` |
| GET | `/v1/volatility?key=&window=1h|24h` | `Volatility` |
| GET | `/v1/candles?key=&tf=15m\|1h\|4h\|1d&from=&to=&limit=300` | `CandleSeries` — velas OHLC do `mid` de uma série (ver "Pregão") |
| GET | `/v1/pregao/stats?keys=a,b` | `SessionStats[]` — resumo do dia (00:00 Assunção) por chave, 1 a 20 chaves |
| GET | `/v1/pregao/sessions` | `HouseSession[]` — status de funcionamento por fonte, inclui referências com `reference: true` |
| GET/POST | `/v1/accounts` | `Account[]` / cria `Account` |
| PATCH | `/v1/accounts/{id}` | atualiza saldos informados manualmente |
| POST | `/v1/simulations/routes` | body `{capital_brl, objective:"cycle|remittance|purchase", destination?:Position, valuation_currency:"BRL", channels:["digital","physical"], amounts?:["5000","10000","25000","50000"]}` → `{opportunities: Opportunity[], search:{amounts_tested, boundaries}}` |
| GET | `/v1/opportunities?capital=&channel=&city=` | `Opportunity[]` (ranking principal + secundário) |
| GET | `/v1/opportunities/cycles?max_len=4&min_roi=` | `Cycle[]` — ciclos no grafo de posições a partir dos saldos estacionados (ver abaixo) |
| GET | `/v1/evidence?source=&from=` / `/v1/evidence/{id}` | `Evidence[]` |
| GET/POST | `/v1/journal` | `JournalEntry[]` |
| GET | `/v1/snapshot` | `{cursor, quotes, sources, opportunities, server_time}` |
| GET | `/v1/stream` | SSE. Header `Last-Event-ID` ou `?cursor=` para replay; `410 Gone` se cursor expirou → cliente refaz snapshot |

## Grafo de posições e ciclos (cruzamento ao vivo)

Nó = `"<moeda>@<venue>"` (venue: id da fonte, `fonte:cidade` para casas de câmbio, id da conta, ou `cash:<cidade>`).
Aresta = cotação (compra: base→quote a `buy`; venda: quote→base a `1/sell`), transferência ou depósito/saque,
com `rate`, `feePct` (sobre a entrada), `feeFixed` (na moeda de saída), `minutes`, `via`, `confidence`, `evidenceId`.
Ciclos simples de 2 a `max_len` arestas são avaliados com o saldo livre do nó inicial.

```jsonc
Cycle { "start": "BRL@brbank", "path": ["BRL@brbank","PYG@ueno","USD@ueno","BRL@brbank"], "edges": [Edge],
        "amountIn": 25000, "amountOut": 25041.2, "gain": 41.2, "roi": 0.001648, "minutes": 4320, "confidence": "estimated" }
```

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
  "source_id": "string", "name": "string", "city": "CDE|ASU|PJC|null", "tz": "string|null",
  "channel": "physical|digital|null", "reference": false,
  "status": "open|closed|pre|unknown",
  "opens_at": "ISO-8601 UTC|null", "closes_at": "ISO-8601 UTC|null", "next_change_at": "ISO-8601 UTC|null",
  "data_mode": "real|simulation|demo"
}
HouseHours {                                             // entrada de backend/src/fronteira_fx/data/market_hours.json; não é resposta de API
  "name": "string|null", "city": "CDE|ASU|PJC|null", "channel": "physical|digital", "tz": "fuso IANA",
  "days": [1, 2, 3, 4, 5, 6], "opens": "HH:MM", "closes": "HH:MM|24:00"
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
- `from` é inclusivo e `to` é exclusivo, sobre `captured_at`. Padrões: `to` = agora (UTC); `from` = `bucket_start(to) − (limit − 1) · grid_s`. Com `from` informado, a janela começa em `from_eff = bucket_start(from)`.
- Corte pela cauda: se a janela tiver mais buckets que `limit`, a resposta traz as últimas `limit` velas, em sequência crescente.
- `from` igual ou posterior a `to` → `422` com `{"detail": "from deve ser anterior a to"}`.
- Sem cotações na janela → `200` com `"candles": []`, nunca 404.
- Valores fora de `tf` ou `limit`, e datas malformadas, são validados pelo FastAPI (422 padrão, com `detail` em lista).
- Chave de série: `{source_id}:{city|digital}:{base}/{quote}:{modality}[:@{branch_id}][:{amount}][:{ctx8}]`. O casamento é por prefixo: `chaco:CDE:USD/PYG:cash` casa com ela mesma e com `chaco:CDE:USD/PYG:cash:@chaco-cde-centro`, mas não com `chaco:CDE:USD/PYG:cash_promo`. Toda consulta filtra `Quote.data_mode == mode`.
- `mid = (buy + sell) / 2` quando os dois lados existem; o lado presente quando só um existe; cotação sem nenhum lado é ignorada.
- Buckets alinhados ao epoch Unix em UTC (o dia começa às 00:00Z): `bucket_start(ts) = epoch(ts) − epoch(ts) mod grid_s`, com `grid_s` = 900 (`15m`), 3600 (`1h`), 14400 (`4h`) e 86400 (`1d`). Uma cotação pertence ao bucket `B` quando `B ≤ captured_at < B + grid_s`.
- Buckets vazios não são emitidos: sem preenchimento e sem repetir o último `c`. A sequência sai crescente por `t`, sem `t` repetido.
- Campos por bucket: `o` é o primeiro mid, `c` o último, `h` o máximo e `l` o mínimo; `n` conta as cotações com mid; `spread_avg` é a média de `sell − buy` nas cotações com os dois lados (`null` se nenhuma), com sinal: negativo indica livro cruzado (Compra acima da Venda); `buy_c` e `sell_c` são o último buy e o último sell não nulos (`null` se nenhum). Os três campos nulos são sempre emitidos, nunca omitidos.
- Sem arredondamento na agregação. Na saída, os decimais têm até 8 casas, com arredondamento ROUND_HALF_EVEN e sem zeros à direita (`"7335"`, não `"7335.00000000"`).

### Resumo da sessão — `GET /v1/pregao/stats`

- `keys`: chaves separadas por vírgula, num único parâmetro. Espaços em volta são removidos e entradas vazias descartadas. São aceitas de 1 a 20 chaves; fora disso, `422` com `{"detail": "keys: informe de 1 a 20 chaves"}`. A resposta traz uma `SessionStats` por chave, na mesma sequência pedida.
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
- `closes ≤ opens` é erro ao carregar o arquivo, com o `source_id` na mensagem: não existe horário que atravesse a meia-noite. Fonte sem horário cadastrado → `unknown`.
- `PRE_OPEN_MIN = 30`: a pré-abertura são os 30 minutos antes de `opens`.
- Rótulos da tela: `open` = "aberta", `closed` = "fechada", `pre` = "pré-abertura", `unknown` = "sem horário".
- Algoritmo do `status` (`now` em UTC; `opens_at`, `closes_at` e `next_change_at` saem em UTC):
  1. Sem horário ou com `tz` inválido → `unknown`, com os três campos de horário `null`.
  2. Sete dias e `00:00`–`24:00` (casa digital sempre aberta) → `open`, com os três campos `null`.
  3. `now` é convertido para o fuso da casa; daí saem o dia da semana e o minuto do dia local.
  4. Dia de funcionamento e `opens ≤ agora < closes` → `open`; `opens_at` e `closes_at` são de hoje; `next_change_at = closes_at`.
  5. Dia de funcionamento e até 30 minutos antes de `opens` → `pre`; `opens_at` e `closes_at` são de hoje; `next_change_at = opens_at`.
  6. Nos demais casos → `closed`. Procura-se o próximo dia de funcionamento, começando por hoje se a pré-abertura de hoje ainda não começou, senão por amanhã, até 8 dias à frente. Encontrado, `opens_at` e `closes_at` são desse dia e `next_change_at = opens_at − 30 min`. Não encontrado (ex.: `days` vazio) → `closed` com os três campos `null`.
  7. Horário local vira UTC pelo fuso da casa; `24:00` é 00:00 do dia seguinte.
- `name` vem de `HouseHours.name`; sem ele, usa `Source.name` e, na falta deste, o `source_id`.
- `reference: true` para fontes `central_bank` (BCP). Referências aparecem na resposta, mas o resumo da tela as deixa fora do total e das casas abertas.

### Modos de dados

- Todo objeto leva `data_mode`, com `real`, `simulation` ou `demo`.
- `real` e `simulation` consultam o banco filtrando por `Quote.data_mode` (e as fontes por `Source.data_mode`).
- `demo` não toca o banco: as três rotas usam geradores determinísticos no servidor. O cliente tem o mesmo gerador para a faixa de demonstração, então os valores batem.

### Compatibilidade

- Enquanto o router `pregao` não estiver publicado em um ambiente, o frontend recorre a `GET /v1/history?key=&grid=300` e agrega localmente com as mesmas regras; nessa aproximação `n` conta pontos de 5 min com `mid`, não cotações.
- `404` em `/v1/candles` ativa esse recurso. `404` em `/v1/pregao/stats` ou `/v1/pregao/sessions` vira lista vazia no cliente.

### Percentuais

- A API devolve percentuais como string já multiplicada por 100: `"0.06816633"` representa 0,07 %. O cliente formata com `formatPercent(v / 100)`.

## Regras do ranking

1. Digital com `net_gain > 0` (após custos conhecidos) entra no ranking principal, mesmo microganho.
2. Físico entra no principal apenas se `roi_fisico >= melhor_roi_digital_comparavel + 0.01` (mesmo capital, objetivo, prazo).
3. `confidence = incomplete` quando falta custo essencial → exibido como estimativa incompleta, nunca como lucro confirmado.

## MCP

Ferramentas espelham os serviços: `list_sources`, `get_quotes`, `request_quote`, `get_history`, `compare_routes`, `simulate_cycle`, `find_cycles`, `search_evidence`.

## Monitoramento ao vivo (sites sem API) — módulo `watch`

Sites sem API não "empurram" dados; o máximo possível é **sondagem inteligente**: requisições condicionais (ETag /
If-Modified-Since), hash do conteúdo relevante para detectar mudança real, intervalo adaptativo (mais curto quando a
fonte muda com frequência ou em horário comercial; recuo exponencial após erros/bloqueio), respeito a limites, e
emissão de evento no stream assim que algo muda.

| Método | Rota | Descrição |
|---|---|---|
| GET | `/v1/watch/sources` | `WatchStatus[]` |
| POST | `/v1/watch/sources/{id}` | body `{interval_s?, enabled?}` — ajuste manual |
| POST | `/v1/watch/run/{id}` | sondagem imediata; retorna `Change | null` |
| GET | `/v1/watch/changes?source=&from=&kind=` | `Change[]` |

```jsonc
WatchStatus { "source_id": "chaco", "enabled": true, "interval_s": 120, "min_interval_s": 60, "max_interval_s": 900,
  "next_run_at": "...", "last_run_at": "...", "last_change_at": "...|null", "changes_24h": 7, "errors_in_row": 0,
  "etag": "string|null", "content_hash": "sha256|null", "status": "ok|degraded|blocked|stale|error|needs_session" }
Change { "id": "uuid", "source_id": "chaco", "ts": "...", "kind": "quote_change|layout_change|status_change",
  "summary": "USD/PYG CDE venda 7350 → 7360", "before": {}, "after": {}, "evidence_id": "uuid|null" }
```
Eventos no stream: `source.change` (payload `Change`) e `alert.fired` (payload `AlertEvent`).
MCP: `watch_status`, `list_changes`, `trigger_poll`.

## Alertas / notificações — módulo `notify`

| Método | Rota | Descrição |
|---|---|---|
| GET/POST | `/v1/alerts/rules` | `AlertRule[]` / cria |
| PATCH/DELETE | `/v1/alerts/rules/{id}` | atualiza / remove |
| GET | `/v1/alerts/events?from=&rule=` | `AlertEvent[]` |
| POST | `/v1/alerts/test/{id}` | envia mensagem de teste pelo canal da regra |

```jsonc
AlertRule { "id": "uuid", "name": "ciclo > 0,2 %", "kind": "cycle_roi|quote_move|source_down|opportunity_new",
  "threshold": "0.002", "params": { "pair": "USD/PYG", "city": "CDE" } | null,
  "channel": "ui|telegram|webhook|email", "target": "chat_id|url|email|null", "cooldown_s": 600, "enabled": true }
AlertEvent { "id": "uuid", "rule_id": "uuid", "ts": "...", "message": "...", "payload": {}, "channel": "telegram",
  "delivered": true, "error": "string|null" }
```
Segredos (token do bot, SMTP) só por variáveis de ambiente do backend. MCP: `list_alert_rules`, `create_alert_rule`.

## RAG (documentação, tarifas, horários, evidências) — módulo `rag`

| Método | Rota | Descrição |
|---|---|---|
| POST | `/v1/rag/documents` | body `{title, text, source, tags[], metadata?}` → `{id, chunks}` |
| GET | `/v1/rag/search?q=&k=5&tag=` | `[{id, document_id, title, snippet, score, source, tags}]` |
| GET | `/v1/rag/documents` | lista resumida |

Cotações e cálculos **nunca** vêm do RAG: vêm do banco e do motor. MCP: `search_knowledge`.

## Memória do agente — módulo `memory`

| Método | Rota | Descrição |
|---|---|---|
| POST | `/v1/memory` | body `{kind: "preference|decision|fact|outcome", text, tags[], ttl_days?}` → `Memory` |
| GET | `/v1/memory?q=&kind=&tag=&limit=` | `Memory[]` (busca textual + tags; mais recentes primeiro) |
| DELETE | `/v1/memory/{id}` | remove |

```jsonc
Memory { "id": "uuid", "kind": "decision", "text": "...", "tags": ["ueno"], "created_at": "...", "expires_at": "...|null", "source": "user|agent" }
```
MCP: `remember`, `recall`, `forget`.
