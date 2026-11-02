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
- `City`: `CDE` (Ciudad del Este) | `ASU` (Asunción) | `PJC` (Pedro Juan Caballero) | `null` (operação digital, sem cidade)
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
  "method": "html", "url": "https://...", "health": "ok", "last_success_at": "...|null", "last_error": "string|null",
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
StreamEvent { "id": "123", "type": "quote.updated|source.health|opportunity.updated|source.change|alert.fired|heartbeat", "ts": "...", "payload": {} }
// payload por tipo (o stream já vem filtrado pelo data_mode da instância):
//   quote.updated       → Quote
//   source.health       → SourceHealth (atualização parcial por source_id; NÃO é um Source completo)
//   opportunity.updated → { "count": 3, "main_ranking": 1, "capitals": ["5000"] } (resumo; o cliente recarrega a lista)
//   source.change       → Change
//   alert.fired         → AlertEvent
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
| GET/POST **[chave]** | `/v1/accounts` | `Account[]` / cria `Account` (POST exige chave) |
| PATCH **[chave]** | `/v1/accounts/{id}` | atualiza saldos informados manualmente |
| POST **[chave]** | `/v1/simulations/routes` | body `{capital_brl, objective:"cycle|remittance|purchase", destination?:Position, valuation_currency:"BRL", channels:["digital","physical"], amounts?:["5000","10000","25000","50000"], persist?:false}` → `{opportunities: Opportunity[], search:{amounts_tested:[string], boundaries:[{low, high, low_winner, high_winner, low_roi_sign, high_roi_sign, reason, refined}]}, simulation_id:"uuid|null"}`. Com `persist`, as linhas são gravadas com `data_mode:"simulation"` (D3) |
| POST **[chave]** | `/v1/simulations/cycle` | body `{capital:"5000", steps:[StepSpec], valuation_currency:"BRL", valuation_rates?:{"USD":"5.40"}}` → `RouteResult`. Aplica cada passo sobre o valor recebido no anterior; `422` se um passo não encadeia |
| GET | `/v1/opportunities?capital=&channel=&city=&kind=` | `Opportunity[]` (ranking principal + secundário) |
| GET | `/v1/opportunities/cycles?max_len=4&min_roi=&start=&limit=200` | `Cycle[]` — ciclos no grafo de posições a partir dos saldos estacionados (ver abaixo) |
| GET | `/v1/evidence?source=&from=&q=&limit=100` / `/v1/evidence/{id}` | `Evidence[]` / `Evidence` (`q` = substring do `excerpt`; `limit` 1..500) |
| GET/POST **[chave]** | `/v1/journal` | `JournalEntry[]` (POST exige chave) |
| GET | `/v1/snapshot` | `{cursor, quotes, sources, opportunities, server_time, data_mode}` |
| GET | `/v1/stream` | SSE. Header `Last-Event-ID` ou `?cursor=` para replay; `410 Gone` se cursor expirou → cliente refaz snapshot |

## Grafo de posições e ciclos (cruzamento ao vivo)

Nó = `"<moeda>@<venue>"` (venue: id da fonte, `fonte:cidade` para casas de câmbio, id da conta, ou `cash:<cidade>`).
Aresta = cotação (compra: base→quote a `buy`; venda: quote→base a `1/sell`), transferência ou depósito/saque,
com `rate`, `fee_pct` (sobre a entrada), `fee_fixed` (na moeda de saída), `minutes`, `via`, `confidence`, `evidence_id`.
Cotações com `kind: market_reference` ou `modality: reference` (BCP, PTAX) **não** viram aresta: servem só de comparação.
Ciclos simples de 2 a `max_len` arestas são avaliados com o saldo livre do nó inicial; uma aresta cuja cotação depende
do montante (`amount_base`) só é usada dentro da faixa em que foi cotada. Dinheiro em string decimal (D1).

Parâmetros de `GET /v1/opportunities/cycles`: `max_len` (2..6, padrão 4), `min_roi` (string decimal, ex. `"0.001"`;
sem ele, ciclos com ganho ≤ 0 também aparecem como "quase lá"), `start` (nó de partida, ex. `BRL@nubank`),
`limit` (1..500, padrão 200). Ordenação: melhor ROI primeiro.

```jsonc
Edge  { "from": "BRL@brbank", "to": "PYG@ueno", "kind": "quote|transfer|deposit|withdraw", "rate": "1366.5",
        "fee_pct": "0", "fee_fixed": "9.9", "minutes": 240, "via": "wu", "confidence": "quoted|estimated|incomplete",
        "evidence_id": "uuid|null" }
Cycle { "start": "BRL@brbank", "path": ["BRL@brbank","PYG@ueno","USD@ueno","BRL@brbank"], "edges": [Edge],
        "amount_in": "25000", "amount_out": "25041.2", "gain": "41.2", "roi": "0.001648", "minutes": 4320,
        "confidence": "estimated", "data_mode": "real|simulation|demo" }
```

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
AlertRule { "id": "uuid", "name": "ciclo > 0,2 %", "kind": "cycle_roi|quote_move|source_down|opportunity_new",
  "threshold": "0.002", "params": { "pair": "USD/PYG", "city": "CDE|digital|null" } | null,   // quote_move compara com Change.after.pair/city;
  //   city "digital" = só cotações sem cidade; ausente/null = qualquer cidade; referências (modality=reference ou
  //   channel=aggregator, ex. dolarPy) nunca disparam quote_move
  "channel": "ui|telegram|webhook|email", "target": "chat_id|url|email|null", "cooldown_s": 600, "enabled": true,
  "last_fired_at": "...|null" }
AlertEvent { "id": "uuid", "rule_id": "uuid", "ts": "...", "message": "...", "payload": {}, "channel": "telegram",
  "delivered": true, "error": "string|null" }
```
Segredos (token do bot, SMTP) só por variáveis de ambiente do backend. MCP: `list_alert_rules`, `create_alert_rule`.

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
