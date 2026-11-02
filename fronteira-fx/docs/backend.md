# Fronteira FX — backend (FastAPI)

Backend do terminal pessoal de câmbio BRL/USD/PYG. Implementa o contrato em `docs/api-contract.md`
(todos os valores monetários como **strings decimais**, datas ISO‑8601 UTC) e expõe:

- API REST `/v1/*` + SSE `/v1/stream` + snapshot `/v1/snapshot`
- Motor financeiro determinístico (`Decimal`, precisão 28, arredondamento só na apresentação)
- Coletor (adapters → cotações + evidências + eventos) com backoff por fonte
- MCP em `/mcp` (fastapi‑mcp) com as ferramentas `list_sources`, `get_quotes`, `request_quote`,
  `get_history`, `compare_routes`, `simulate_cycle`, `search_evidence`
- Modo demo isolado (`data_mode="demo"` em todas as linhas; nunca misturado com dados reais)

Código: `backend/src/fronteira_fx/`

```
config.py          settings (pydantic-settings) — variáveis de ambiente abaixo
db.py / models.py  SQLAlchemy 2.0 (SQLite para dev/testes, Postgres+pgvector no compose)
schemas.py         Pydantic v2 espelhando o contrato (Decimal → string)
engine/            positions, routes, ranking, search, volatility, cards  (puro, sem I/O)
services/          events (cursor/replay/410), quotes, history, opportunities, collector, worker, demo
api/               routers /v1 (health, sources, quotes, history, accounts, simulations,
                   opportunities, evidence, journal, snapshot, stream)
mcp.py             montagem do servidor MCP
main.py            create_app() / app
alembic/           migrações (0001_initial)
scripts/           export_openapi.py, backup.sh, restore.sh
```

## Instalação e execução local

```bash
cd backend
uv sync                              # dependências (Python 3.13)
cp .env.example .env                 # opcional; defaults usam SQLite em ./var/fx.db
uv run alembic upgrade head          # cria o schema (ou deixe AUTO_CREATE_SCHEMA=true criar no boot)
uv run uvicorn fronteira_fx.main:app --reload   # API em http://localhost:8000
# ou: uv run fastapi dev            (entrypoint declarado em [tool.fastapi])
```

Docs interativas: `http://localhost:8000/docs`. Spec exportada: `docs/openapi.json`
(`uv run python scripts/export_openapi.py`).

Worker (coletor): `uv run python -m fronteira_fx.services.worker` (ou `uv run fronteira-fx-worker`).
Ele acorda a cada `WORKER_TICK_S` e só consulta fontes cujo `next_poll_at` venceu (backoff exponencial
após falhas: `poll_interval * 2^(n-1)`, teto `BACKOFF_MAX_S`). Também processa a fila de
`POST /v1/quotes/request` para fontes que exigem navegador e poda o stream de eventos.

Modo demo: `DATA_MODE=demo uv run uvicorn fronteira_fx.main:app` — semeia dados ilustrativos
(ids prefixados `demo-`, nomes com "(demo)") e serve só eles; `/v1/health` reporta `data_mode`.
`FX_SEED_DEMO=1` semeia o demo num banco vazio mesmo em modo real (as linhas ficam invisíveis até
alguém subir uma instância com `DATA_MODE=demo`).

Testes e lint:

```bash
uv run ruff check src tests
uv run pytest -q
```

## Variáveis de ambiente

| Variável | Default | Descrição |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./var/fx.db` | SQLAlchemy URL. Postgres: `postgresql+psycopg://fx:fx@host:5432/fx` |
| `AUTO_CREATE_SCHEMA` | `true` | `create_all` no boot (dev). Em produção use alembic e `false` |
| `DATA_MODE` | `real` | `real` ou `demo`; filtra todas as consultas |
| `FX_SEED_DEMO` | `0` | semeia demo se o banco estiver vazio |
| `CORS_ORIGINS` | `http://localhost:3000,...` | lista separada por vírgula |
| `API_KEY` | vazio | se definido, exige `X-API-Key` (ou `Authorization: Bearer`) em `/mcp` e nos endpoints de escrita |
| `POLL_INTERVAL_S` | `300` | intervalo padrão de coleta |
| `WORKER_TICK_S` | `30` | frequência do loop do worker |
| `BACKOFF_MAX_S` | `3600` | teto do backoff por fonte |
| `EVENT_RETENTION` | `20000` | máximo de eventos retidos |
| `EVENT_RETENTION_S` | `86400` | idade máxima dos eventos |
| `STREAM_MAX_DURATION_S` | `55` | duração máxima de uma conexão SSE (cliente reconecta pelo cursor) |
| `STREAM_HEARTBEAT_S` | `15` | heartbeat SSE |
| `QUOTES_LOOKBACK_S` | `604800` | janela do "mais recente por contexto" |
| `EVIDENCE_DIR` | `./var/evidence` | onde o worker guarda payloads brutos |

## Stream SSE (`/v1/stream`)

- `GET /v1/snapshot` devolve `cursor`; conecte com `GET /v1/stream?cursor=<n>` (ou header
  `Last-Event-ID`, que o `EventSource` envia sozinho ao reconectar).
- Cada evento tem `id:` (cursor) e `data:` = `StreamEvent` JSON (`type`: `quote.updated`,
  `source.health`, `opportunity.updated`, `heartbeat`). Não é enviado o campo `event:`, então
  `EventSource.onmessage` recebe tudo.
- `410 Gone` quando o cursor é anterior à janela retida → refaça o snapshot.
- A conexão fecha de forma limpa após `STREAM_MAX_DURATION_S`; o cliente reconecta com o último id.

## Chaves de série (`/v1/history`, `/v1/volatility`)

`{source}:{cidade|digital}:{BASE}/{QUOTE}:{modalidade}[:@filial][:montante][:ctx8]` — ex.:
`chaco:CDE:USD/PYG:cash:@chaco-cde-centro`. Cada `Quote` traz sua `series_key`. Uma chave sem os
sufixos (`chaco:CDE:USD/PYG:cash`) funciona como prefixo e agrega as séries abaixo dela.

Volatilidade: grade de 5 min, janelas 1h/24h, desvio‑padrão amostral dos log‑retornos entre células
adjacentes (`% por intervalo de 5 min`), mínimo 6 retornos (`insufficient_data`); recapturas da mesma
cotação (mesmo `declared_updated_at`) não contam como observação (`stale_input`).

## Ranking e simulações

`POST /v1/simulations/routes` monta rotas a partir das últimas cotações (`buy` = casa compra a base ⇒
base→quote a `buy`; quote→base a `1/sell`; `market_reference` nunca é perna executável), simula cada
rota (taxas nunca duplicadas, custo desconhecido ⇒ `confidence=incomplete` + `pending_costs`) e aplica:

1. digital com `net_gain > 0` entra no ranking principal (mesmo microganho);
2. físico só entra se `roi >= melhor_roi_digital_comparável + 0.01` (mesmo capital/objetivo/prazo);
   digitais `incomplete` não servem de régua;
3. `incomplete` é sempre exibido como estimativa incompleta.

A busca adaptativa testa 5.000/10.000/25.000/50.000 (só montantes suportados pelo provedor) e
bisseciona onde o vencedor ou o sinal do ROI muda (≤ 12 avaliações) → `search.amounts_tested`,
`search.boundaries`. `objective=remittance|purchase` produz `remittance_saving|purchase_saving`
relativos à pior rota comparável (referência).

`POST /v1/simulations/cycle` simula passos explícitos (ferramenta MCP `simulate_cycle`).

## Docker Compose (Postgres + pgvector, API, worker)

```bash
cd fronteira-fx
docker compose up -d --build        # postgres (pgvector/pgvector:pg16), api :8000, worker (Playwright)
docker compose logs -f api worker
```

A API roda `alembic upgrade head` ao subir. Variáveis `.env` na raiz são lidas pelo compose
(`POSTGRES_*`, `DATA_MODE`, `CORS_ORIGINS`, `API_KEY`, ...).

### Backup / restore

```bash
backend/scripts/backup.sh ./backups                 # pg_dump --format=custom via `docker compose exec`
backend/scripts/restore.sh ./backups/fx-<stamp>.dump # pg_restore --clean (destrói os dados atuais!)
# fora do compose: DATABASE_URL=postgresql+psycopg://... backend/scripts/backup.sh
```

## Apontar o frontend (Vercel) para o backend

No projeto Vercel defina `NEXT_PUBLIC_API_URL=https://<seu-host>:8000` (ou o domínio do túnel/reverse
proxy) e inclua a origem do frontend em `CORS_ORIGINS` do backend
(`https://<app>.vercel.app,http://localhost:3000`). O frontend usa `GET /v1/snapshot` e depois
`/v1/stream`; se o backend exigir `API_KEY`, apenas escritas e `/mcp` precisam do header.

## MCP

`/mcp` (transporte HTTP, fastapi‑mcp). Ferramentas: `list_sources`, `get_quotes`, `request_quote`,
`get_history`, `compare_routes`, `simulate_cycle`, `search_evidence`. Com `API_KEY` definido, envie
`X-API-Key` (ou `Authorization: Bearer`).

## Notas de implementação

- Dinheiro: `Numeric(24,8)` no Postgres; no SQLite o `TypeDecorator Money` grava strings decimais
  canônicas (exatidão garantida nos dois).
- `documents.embedding`: `Vector(1536)` (pgvector) no Postgres, JSON no SQLite.
- `quote_events.id` é o cursor SSE; `events.prune()` aplica retenção; cursor anterior ⇒ `CursorExpired` ⇒ 410.
- O coletor importa `fronteira_fx.adapters.registry` de forma preguiçosa; sem registry = sem adapters.
- `fastapi-mcp 0.4.x` exige `mcp<2` (fixado no `pyproject.toml`).
