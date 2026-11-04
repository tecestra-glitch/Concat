# Fronteira FX — backend (FastAPI)

Backend do terminal pessoal de câmbio BRL/USD/PYG. Implementa o contrato em `docs/api-contract.md`
(todos os valores monetários como **strings decimais**, datas ISO‑8601 UTC) e expõe:

- API REST `/v1/*` + SSE `/v1/stream` + snapshot `/v1/snapshot`
- Motor financeiro determinístico (`Decimal`, precisão 28, arredondamento só na apresentação)
- Coletor (adapters → cotações + evidências + eventos) com GET condicional, piso de 60 s por fonte e backoff
- Grafo de posições e ciclos a partir de saldos estacionados (`/v1/opportunities/cycles`)
- Pilha pública = routers `api/*` (D7), inclusive sondagem inteligente + log de mudanças (`/v1/watch`), regras de
  alerta ui/telegram/webhook/email (`/v1/alerts`), corpus com busca léxica (`/v1/rag`) e memória do agente
  (`/v1/memory`). Os pacotes `watch/`, `notify/`, `rag/`, `memory/` e `graph/` são **biblioteca**: seus `router.py`
  não são montados (`tests/api/test_mounting.py` falha se forem, ou se houver `operationId` duplicado) e seus stores
  SQL ficam fora do Alembic (ver [Alembic e stores de módulo](#alembic-e-stores-de-módulo-d7))
- MCP em `/mcp` (fastapi‑mcp): 18 ferramentas; lista, marcação leitura/escrita e autenticação em [`docs/mcp.md`](./mcp.md)
- Modos de dados `real` | `simulation` | `demo` (`data_mode` em toda linha; nunca misturados)

Código: `backend/src/fronteira_fx/`

```
config.py          settings (pydantic-settings) — variáveis de ambiente abaixo
db.py / models.py  SQLAlchemy 2.0 (SQLite para dev/testes, Postgres+pgvector no compose)
schemas.py         Pydantic v2 espelhando o contrato (Decimal → string)
engine/            positions, routes, ranking, search, volatility, cards, graph  (puro, sem I/O)
services/          events (cursor/replay/410), quotes, history, opportunities, cycles, watch, alerts, rag,
                   collector, worker, demo
api/               routers /v1 montados em main.py (health, sources, quotes, history, accounts, simulations,
                   opportunities[/cycles], evidence, journal, snapshot, stream, watch, alerts, rag, memory)
watch/ notify/ rag/ memory/ graph/
                   biblioteca: fetcher (GET condicional), canais, embeddings, stores próprios; routers NÃO montados
mcp.py             montagem do servidor MCP (`MCP_OPERATIONS`)
cli.py             `seed-knowledge` (semeia backend/knowledge/*.md no RAG)
main.py            create_app() / app
alembic/           migrações (0001_initial) — só `models.Base`
scripts/           export_openapi.py, backup.sh, restore.sh
```

## Instalação e execução local

```bash
cd backend
uv sync                              # dependências (Python 3.13)
cp ../.env.example .env              # opcional; só placeholders; defaults usam SQLite em ./var/fx.db
uv run alembic upgrade head          # cria o schema (ou deixe AUTO_CREATE_SCHEMA=true criar no boot)
uv run uvicorn fronteira_fx.main:app --reload   # API em http://localhost:8000
# ou: uv run fastapi dev            (entrypoint declarado em [tool.fastapi])
```

Docs interativas: `http://localhost:8000/docs`. Spec exportada: `docs/openapi.json`
(`uv run python scripts/export_openapi.py`; o CI falha se o arquivo divergir).

Worker (coletor): `uv run python -m fronteira_fx.services.worker` (ou `uv run fronteira-fx-worker`).
Ele acorda a cada `WORKER_TICK_S` e só consulta fontes cujo `next_poll_at` venceu (backoff exponencial
após falhas: `poll_interval * 2^(n-1)`, teto `BACKOFF_MAX_S`). Também processa a fila de
`POST /v1/quotes/request` para fontes que exigem navegador e poda o stream de eventos. **Piso de 60 s por
fonte (D6):** `collect(..., force=True)` respeita `last_run_at + 60 s` — dentro da janela devolve o último
resultado conhecido sem nova requisição, e o endpoint/MCP responde `429` com `Retry-After` quando o chamador
exigiu sondagem nova (vale para `trigger_poll` e `request_quote`). O slot é reservado (`last_run_at`) na mesma
transação da verificação, com trava de linha no Postgres, antes de qualquer requisição: chamadas simultâneas (na api
ou entre api e worker) fazem uma única requisição ao provedor e as demais recebem `429`. As sondagens agendadas dos
adaptadores html de parse puro que declaram `conditional_get = True` (hoje `maxicambios` e `myd`) são condicionais
(`watch/fetcher.conditional_get` com `etag`/`last_modified` de `watch_states`); `304` não gera evidência nova. Os
demais adaptadores fazem a própria requisição (formulários, APIs JSON, navegador) e o hash do conteúdo evita
capturas repetidas.

Modo demo: `DATA_MODE=demo uv run uvicorn fronteira_fx.main:app` — semeia dados ilustrativos
(ids prefixados `demo-`, nomes com "(demo)") e serve só eles; `/v1/health` reporta `data_mode`.
`FX_SEED_DEMO=1` semeia o demo num banco vazio mesmo em modo real (as linhas ficam invisíveis até
alguém subir uma instância com `DATA_MODE=demo`).

Modo simulação (D3): `POST /v1/simulations/routes` e `/cycle` gravam `Simulation`/`Opportunity` com
`data_mode="simulation"` (e `simulation_id`); `list_opportunities` filtra `simulation_id IS NULL` **e** o
`data_mode` pedido, então o ranking real nunca vê simulações. Esses dois endpoints exigem `X-API-Key` quando
`API_KEY` está definido.

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
| `DATA_MODE` | `real` | `real`, `simulation` ou `demo` (`DataMode` em `config.py`); filtra todas as consultas. `simulation` é o `data_mode` gravado por `POST /v1/simulations/*` |
| `FX_SEED_DEMO` | `0` | semeia demo se o banco estiver vazio |
| `PLAN_QUOTE_MAX_AGE_S` | `900` | idade máxima (s) da cotação mais velha de um plano antes de ele expirar, enquanto a execução não começou |
| `CORS_ORIGINS` | `http://localhost:3000,...` | lista separada por vírgula; só importa quando o navegador fala direto com a API (dev sem chave) |
| `API_KEY` | vazio | se definido, exige `X-API-Key` (ou `Authorization: Bearer`) em todo `/mcp` e nos endpoints de escrita, inclusive `POST /v1/simulations/*` |
| `POLL_INTERVAL_S` | `300` | intervalo padrão de coleta (piso efetivo de 60 s por fonte, mesmo com `force`) |
| `WORKER_TICK_S` | `30` | frequência do loop do worker |
| `BACKOFF_MAX_S` | `3600` | teto do backoff por fonte |
| `EVENT_RETENTION` | `20000` | máximo de eventos retidos |
| `EVENT_RETENTION_S` | `86400` | idade máxima dos eventos |
| `STREAM_MAX_DURATION_S` | `55` | duração máxima de uma conexão SSE (cliente reconecta pelo cursor) |
| `STREAM_HEARTBEAT_S` | `15` | heartbeat SSE |
| `QUOTES_LOOKBACK_S` | `604800` | janela do "mais recente por contexto" e das cotações usadas pelo grafo de ciclos |
| `EVIDENCE_DIR` | `./var/evidence` | onde o worker guarda payloads brutos (lido de `settings.evidence_dir`). Alias legado `FX_EVIDENCE_DIR`, aceito com aviso |
| `WATCH_MIN_INTERVAL_S` / `WATCH_MAX_INTERVAL_S` | `60` / `900` | limites do intervalo adaptativo por fonte |
| `TELEGRAM_BOT_TOKEN` | vazio | canal `telegram` dos alertas (target = chat_id) |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_STARTTLS` | — / `587` / — / — / — / `true` | canal `email` |
| `ALERT_HTTP_TIMEOUT_S` | `10` | timeout de webhook/telegram/smtp |

Modelo completo com placeholders em `fronteira-fx/.env.example` (versionado; o `.env` real nunca é versionado).

## Stream SSE (`/v1/stream`)

- `GET /v1/snapshot` devolve `cursor` (e `data_mode`); conecte com `GET /v1/stream?cursor=<n>` (ou header
  `Last-Event-ID`, que o `EventSource` envia sozinho ao reconectar).
- Cada evento tem `id:` (cursor) e `data:` = `StreamEvent` JSON (`type`: `quote.updated`,
  `source.health`, `opportunity.updated`, `source.change`, `alert.fired`, `heartbeat`). Não é enviado o campo `event:`, então
  `EventSource.onmessage` recebe tudo.
- `410 Gone` quando o cursor é anterior à janela retida → refaça o snapshot.
- A conexão fecha de forma limpa após `STREAM_MAX_DURATION_S`; o cliente reconecta com o último id.

## Chaves de série (`/v1/history`, `/v1/volatility`)

`{source}:{cidade|digital}:{BASE}/{QUOTE}:{modalidade}[:@filial][:montante][:ctx8]` — ex.:
`chaco:CDE:USD/PYG:cash:@chaco-cde-centro`. Cada `Quote` traz sua `series_key` (D2), e `GET /v1/history?key=`
recebe exatamente esse valor. Uma chave sem os sufixos (`chaco:CDE:USD/PYG:cash`) funciona como prefixo e agrega
as séries abaixo dela.

Volatilidade: grade de 5 min, janelas 1h/24h, desvio‑padrão amostral dos log‑retornos entre células
adjacentes (`% por intervalo de 5 min`), mínimo 6 retornos (`insufficient_data`); recapturas da mesma
cotação (mesmo `declared_updated_at`) não contam como observação (`stale_input`).

## Ranking e simulações

`POST /v1/simulations/routes` monta rotas a partir das últimas cotações (`buy` = casa compra a base ⇒
base→quote a `buy`; quote→base a `1/sell`; `market_reference` nunca é perna executável; cotações com
`modality="reference"`, como as do agregador dolarPy, ficam fora do ranking e do grafo), simula cada
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

### Grafo de posições (`GET /v1/opportunities/cycles?max_len=4&min_roi=&start=&limit=`)

Nós `<moeda>@<venue>` (venue = id da fonte digital, `fonte:cidade` para casas de câmbio, instituição da conta,
`cash:<cidade>` para dinheiro vivo nas seis cidades CDE, ASU, PJC, ENC, FOZ e PPO). Arestas: cotações (`buy`/`1/sell`,
com `mid_rate` para medir o spread), transferências conta↔lugar digital e conta↔casa (priceadas por
`data/rails.json`), balcão `cash:<cidade>`↔casa de câmbio, saques ATM (trilho `->cash`) e deslocamento entre cidades
(`kind: travel`, `data/transport.json`, uma aresta por moeda e sentido). Trilho ou rota sem valor `null` ⇒
`incomplete`, nunca zero. Cada aresta carrega `fee_pct`, `fee_fixed`, `iof_pct`, `transport_fixed`, `minutes`,
`confidence`, `evidence_id`, `channel` e a faixa `min_in`/`max_in` do contexto da cotação ou do trilho. Ciclos simples
de 2..`max_len` arestas (`max_len` 2..6, padrão 4) são avaliados com o saldo livre do nó inicial
(`x = x·(1−fee_pct−iof_pct)·rate − fee_fixed − transport_fixed`), melhor ROI primeiro; `limit` 1..500 (padrão 200);
`min_roi` é string decimal. Cada ciclo expõe `legs[]` (custos por perna na moeda de origem), `gain_by_currency`
(BRL, USD, PYG), `costs` na moeda de partida e `requires_declaration`, calculados por `services.cycles.enrich_cycle`
com as taxas de valoração BRL (`derive_valuation_rates`). Como no contrato (D1), `Cycle`/`Edge` usam **snake_case e
strings decimais** e trazem `data_mode`. Ver `docs/arbitragem.md` para o modelo completo.

## Módulo `watch` (sondagem inteligente)

Estado por fonte em `watch_states` (`GET /v1/watch/sources`): intervalo adaptativo entre `min_interval_s` e
`max_interval_s` — mudança real de preço ⇒ intervalo/2; nada mudou ⇒ ×1,5; erro/bloqueio ⇒ dobra (teto `BACKOFF_MAX_S`).
`content_hash` = sha256 da evidência (mesma página ⇒ sem novos eventos); `etag`/`last_modified` alimentam o GET
condicional. Mudanças (`quote_change` com `before/after` estruturados, inclusive `pair` e `city`; `layout_change`;
`status_change`) ficam em `changes` (`GET /v1/watch/changes?source=&from=&kind=`) e saem no stream como
`source.change`. `POST /v1/watch/sources/{id}` ajusta `interval_s`/`enabled`. `POST /v1/watch/run/{id}` sonda agora
(D4/D6): `404` fonte desconhecida; `409` quando `data_mode != real` (o `detail` explica); `429` + `Retry-After`
dentro do piso de 60 s por fonte, **também com `force=true`**; `200` com a primeira `Change` ou `null` quando nada
mudou.

## Módulo `notify` (alertas)

`/v1/alerts/rules` (CRUD) com `kind`: `cycle_roi` (melhor ciclo do ranking principal ≥ `threshold`; `params.capital`
opcional), `quote_move` (variação relativa ≥ `threshold` numa `Change`, comparando `pair`/`city` estruturados de
`Change.after`), `source_down` (fonte passou a blocked/error/needs_session), `opportunity_new` (nova oportunidade no
ranking principal), `cycle_net_gain` (ganho líquido positivo ≥ `threshold` numa moeda de `params.currency`, só para
ciclos `quoted`/`estimated`). Avaliadas após cada coleta, com `cooldown_s`. Canais: `ui` (só grava), `webhook` (POST JSON para
qualquer URL — por isso as escritas exigem `API_KEY`), `telegram` (Bot API), `email` (SMTP). Eventos em
`/v1/alerts/events` e no stream (`alert.fired`); `POST /v1/alerts/test/{id}` envia um teste.

## Módulo `plans` (planos de execução, fase A)

`services/plans.py`, rotas em `api/plans.py`, tabelas `execution_plans` e `execution_steps` (migração `0003`). Um plano
nasce de um ciclo atual (`POST /v1/plans` com `start` e `path`) e guarda um snapshot: arestas, pernas, custos, cotações
usadas e `data_mode`. A máquina de estados e os textos estão em `docs/api-contract.md`. **Nenhuma rota executa
movimentação**: `approve` e `steps/{n}/done` só gravam o que o dono decidiu ou informou. A expiração olha a idade da
cotação mais velha (`PLAN_QUOTE_MAX_AGE_S`) e só vale antes do primeiro passo. Ao concluir, o resultado (esperado ×
realizado) vai para `journal_entries` com `kind: "result"`.

Dados versionados do motor: `data/transport.json` (rotas entre cidades) e `data/rails.json` (trilhos de transferência),
carregados por `services/logistics.py` com pydantic, `lru_cache` e erro com o id da linha. Campos `null` e
`verified: false` são o estado inicial: a fase B preenche com fonte (`source_url`, `checked_at`). Ver `docs/arbitragem.md`.

## RAG e memória

`POST /v1/rag/documents` divide o texto em chunks (`document_chunks`) e `GET /v1/rag/search?q=&k=&tag=` faz busca
**léxica** tf‑idf (sem acentos, stopwords pt/es/en). Embeddings e pgvector existem só no módulo `rag/` (`rag/store.py`,
`rag/embeddings.py`), **não montado** no app; nenhum provedor de embeddings está ligado no núcleo e a coluna
`documents.embedding` fica vazia. Cotações e cálculos nunca vêm do RAG. O corpus inicial (`backend/knowledge/*.md`:
casas, fintechs, glossário, regras do produto) é semeado de forma idempotente (hash por arquivo) no startup e por
`uv run python -m fronteira_fx.cli seed-knowledge`.

`/v1/memory` guarda `preference|decision|fact|outcome` com tags e `ttl_days`; `GET /v1/memory` filtra por texto/kind/tag
(limite 1..100, padrão 20; `%`/`_` escapados) e ignora expiradas; `GET /v1/memory/summary` devolve um resumo curto
pronto para o contexto do agente (ferramenta MCP `memory_summary`). Detalhes em `docs/memoria.md`.

## Alembic e stores de módulo (D7)

O Alembic (`backend/alembic/`, `0001_initial`) cobre **só `models.Base`**; `tests/test_alembic.py` roda `upgrade head`
+ `alembic check` num SQLite temporário e falha quando um model muda sem migração. Os stores dos pacotes de módulo
têm bases próprias e criam suas tabelas por conta própria (`create_notify_tables`, `create_memory_tables`, …) apenas
quando alguém os usa como biblioteca: `notify/store.py` (`notify_alert_rules`/`notify_alert_events`, renomeadas em D7
para não colidir com `alert_rules`/`alert_events` de `models.py`), `memory/store.py` (`agent_memories`),
`rag/store.py` (`rag_documents`/`rag_chunks`) e `watch/store_sql.py` (`watch_status`/`watch_changes`). Essas tabelas
**não entram no Alembic** e não existem numa instância padrão; o que a API pública usa são as tabelas de `models.py`
(`watch_states`, `changes`, `alert_rules`, `alert_events`, `documents`, `document_chunks`, `memories`).

## Docker Compose (Postgres + pgvector, API, worker, web opcional)

```bash
cd fronteira-fx
cp .env.example .env                        # POSTGRES_PASSWORD e API_KEY obrigatórios (sem default fraco)
docker compose up -d --build                # postgres (pgvector 0.8.7-pg16, pinado por digest), api :8000, worker (Playwright)
docker compose --profile web up -d --build  # + web (Next.js standalone, FX_API_URL=http://api:8000, FX_API_KEY do .env)
docker compose logs -f api worker
```

A API roda `alembic upgrade head` ao subir e expõe healthcheck em `/v1/health`; o worker só sobe depois de a API
estar saudável. Variáveis do `.env` são lidas pelo compose (`POSTGRES_*`, `DATA_MODE`, `CORS_ORIGINS`, `API_KEY`,
`EVIDENCE_DIR`, Telegram/SMTP, ...). Detalhes em [`docs/deploy.md`](./deploy.md).

### Backup / restore

```bash
backend/scripts/backup.sh ./backups                 # pg_dump --format=custom via `docker compose exec`
backend/scripts/restore.sh ./backups/fx-<stamp>.dump # pg_restore --clean (destrói os dados atuais!)
# fora do compose: DATABASE_URL=postgresql+psycopg://... backend/scripts/backup.sh
```

## Apontar o frontend para o backend (D5: proxy server-side)

O navegador nunca chama a API diretamente: a rota `src/app/api/fx/[...path]/route.ts` do Next.js (server-side) lê
`FX_API_URL` e `FX_API_KEY`, injeta `X-API-Key` e repassa `GET/POST/PATCH/DELETE`, query string, `data_mode` e o stream
SSE. O cliente usa a base `/api/fx` por padrão.

- Local: `FX_API_URL=http://localhost:8000` e, se o backend tiver `API_KEY`, `FX_API_KEY` com o mesmo valor, em
  `fronteira-fx/.env.local`.
- Vercel: `FX_API_URL` (URL **HTTPS** pública da API — o uvicorn serve HTTP puro na 8000, então coloque TLS na frente)
  e `FX_API_KEY`, como variáveis de servidor, separadamente em Preview e Production. Nada com prefixo `NEXT_PUBLIC_`.
- `CORS_ORIGINS` só importa no modo de dev em que `NEXT_PUBLIC_API_URL` faz o navegador falar direto com a API (sem
  chave); com o proxy, as URLs de preview não precisam constar nele.

## MCP

`/mcp` (transporte HTTP, fastapi‑mcp). Ferramentas, marcação leitura/escrita e configuração do cliente em
[`docs/mcp.md`](./mcp.md). Com `API_KEY` definido, todo `/mcp` exige `X-API-Key` (ou `Authorization: Bearer`).

## Notas de implementação

- Dinheiro: `Numeric(24,8)` no Postgres; no SQLite o `TypeDecorator Money` grava strings decimais
  canônicas (exatidão garantida nos dois).
- `documents.embedding`: `Vector(1536)` (pgvector) no Postgres, JSON no SQLite — coluna reservada, nunca preenchida pelo núcleo.
- `quote_events.id` é o cursor SSE; `events.prune()` aplica retenção; cursor anterior ⇒ `CursorExpired` ⇒ 410.
- O coletor importa `fronteira_fx.adapters.registry` de forma preguiçosa; sem registry = sem adapters.
- `fastapi-mcp 0.4.x` exige `mcp<2` (fixado no `pyproject.toml`).
