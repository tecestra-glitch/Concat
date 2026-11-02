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
  "poll_interval_s": 300, "data_mode": "real|demo"
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
  "evidence_id": "uuid", "data_mode": "real|demo"
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
  "comparable_best_digital_roi": "0.0071|null", "computed_at": "...", "data_mode": "real|demo"
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
| GET/POST | `/v1/accounts` | `Account[]` / cria `Account` |
| PATCH | `/v1/accounts/{id}` | atualiza saldos informados manualmente |
| POST | `/v1/simulations/routes` | body `{capital_brl, objective:"cycle|remittance|purchase", destination?:Position, valuation_currency:"BRL", channels:["digital","physical"], amounts?:["5000","10000","25000","50000"]}` → `{opportunities: Opportunity[], search:{amounts_tested, boundaries}}` |
| GET | `/v1/opportunities?capital=&channel=&city=` | `Opportunity[]` (ranking principal + secundário) |
| GET | `/v1/evidence?source=&from=` / `/v1/evidence/{id}` | `Evidence[]` |
| GET/POST | `/v1/journal` | `JournalEntry[]` |
| GET | `/v1/snapshot` | `{cursor, quotes, sources, opportunities, server_time}` |
| GET | `/v1/stream` | SSE. Header `Last-Event-ID` ou `?cursor=` para replay; `410 Gone` se cursor expirou → cliente refaz snapshot |

## Regras do ranking

1. Digital com `net_gain > 0` (após custos conhecidos) entra no ranking principal, mesmo microganho.
2. Físico entra no principal apenas se `roi_fisico >= melhor_roi_digital_comparavel + 0.01` (mesmo capital, objetivo, prazo).
3. `confidence = incomplete` quando falta custo essencial → exibido como estimativa incompleta, nunca como lucro confirmado.

## MCP

Ferramentas espelham os serviços: `list_sources`, `get_quotes`, `request_quote`, `get_history`, `compare_routes`, `simulate_cycle`, `search_evidence`.
