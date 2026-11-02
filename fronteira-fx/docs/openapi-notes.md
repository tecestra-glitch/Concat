# OpenAPI — notas do módulo pregao

Notas para quem regenera ou lê `docs/openapi.json` sobre as três rotas do pregão. O contrato em prosa, com regras e exemplos, está em `docs/api-contract.md`, seção "Pregão — velas, resumo da sessão e horários das casas".

## Operações

| `operation_id` | Rota | `response_model` |
|---|---|---|
| `get_candles` | `/v1/candles` | `CandleSeries` |
| `get_pregao_stats` | `/v1/pregao/stats` | `list[SessionStats]` |
| `get_pregao_sessions` | `/v1/pregao/sessions` | `list[HouseSession]` |

- Tag: `pregao`.
- Sem `ApiKey`: as três rotas não exigem chave de API no OpenAPI.
- `HouseHours` não aparece no OpenAPI. É o formato de cada entrada de `market_hours.json`, não uma resposta de API.

## Regeneração

- Comando: `cd backend && uv run python scripts/export_openapi.py`. Ele grava `docs/openapi.json` (ou o caminho passado como argumento).
- As três rotas só aparecem depois que `api/__init__.py` registra o router `candles`. Esse registro é passo da integração, não desta unidade. Antes dele, o arquivo gerado não contém `/v1/candles`, `/v1/pregao/stats` nem `/v1/pregao/sessions`.

## Validação manual

Depois da integração, o comando abaixo deve listar as três rotas:

```
cd backend && uv run python -c "from fronteira_fx.main import app; print(sorted(p for p in app.openapi()['paths'] if 'candles' in p or 'pregao' in p))"
```

## Convenções

- Datas em ISO 8601 com offset: `Z` para UTC e `-03:00` para `America/Asuncion`.
- Decimais (preços, spreads, percentuais) trafegam como `string`, nunca como `number`.
- `data_mode` é obrigatório em todo objeto, com os valores `real`, `simulation` ou `demo`.
- `from` e `to` são aliases dos parâmetros Python `start` e `end`.
- `keys` em `/v1/pregao/stats` vem como um único parâmetro com valores separados por vírgula.
- Erros: validação do FastAPI retorna `422` com `detail` em lista. As duas regras próprias retornam `422` com `detail` em string: `from deve ser anterior a to` e `keys: informe de 1 a 20 chaves`.
