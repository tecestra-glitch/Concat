# Deploy — Fronteira FX

## Visão geral

| Peça | Onde roda | Por quê |
|---|---|---|
| `postgres` (PostgreSQL 16 + pgvector) | container | estado: cotações, evidências indexadas, memória, RAG |
| `api` (FastAPI + alembic + `/mcp`) | container | processo persistente; serve `/v1/*` e o stream SSE |
| `worker` (coletor + Playwright/Chromium) | container | loop indefinido com navegador; não cabe em funções serverless |
| frontend (Next.js) | Vercel **ou** container (`--profile web`) | só UI + proxy server-side para a API |

O navegador nunca fala com a API diretamente nem conhece a chave: toda chamada passa pelo proxy
server-side do Next.js (`src/app/api/fx/[...path]`), que lê `FX_API_URL` e `FX_API_KEY` no servidor e
injeta `X-API-Key`. Segredos ficam só no backend e nesse proxy, por variáveis de ambiente — nunca em
`NEXT_PUBLIC_*`, nunca no Git.

## Subida local com Docker Compose

Pré-requisitos: Docker Engine com Compose v2 (BuildKit ativo) e `openssl` para gerar segredos.
Tudo roda a partir de `fronteira-fx/`.

```bash
cd fronteira-fx
cp .env.example .env
# gere os dois segredos obrigatórios (só hexadecimal: não quebra a URL de conexão)
sed -i "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$(openssl rand -hex 32)/" .env
sed -i "s/^API_KEY=.*/API_KEY=$(openssl rand -hex 32)/" .env

docker compose config -q            # valida; falha se POSTGRES_PASSWORD ou API_KEY faltarem
docker compose up -d --build        # postgres → api (migrações) → worker
docker compose ps                   # api e postgres devem aparecer "healthy"
curl -fsS http://127.0.0.1:8000/v1/health
docker compose logs -f api worker
```

Ordem de arranque (garantida por `depends_on` + healthchecks): `postgres` fica saudável
(`pg_isready`) → `api` roda `alembic upgrade head` e sobe o uvicorn → o healthcheck em `/v1/health`
passa → só então o `worker` parte, já com o esquema migrado.

Padrões de segurança do compose:

- `POSTGRES_PASSWORD` e `API_KEY` são **obrigatórias** (`${VAR:?...}`): sem `.env` o compose recusa
  subir em vez de usar senha `fx` ou API sem chave.
- A API e o Postgres só são publicados em `127.0.0.1` (`API_BIND`/`API_PORT`, `POSTGRES_PORT`).
  Para expor a API, coloque um proxy TLS no host (abaixo), não mude `API_BIND` para `0.0.0.0`.
- Os containers `api`, `worker` e `web` rodam sem root (`api` e `worker` com o mesmo UID 10001, porque
  partilham o volume `evidence`); as imagens são pinadas por digest.
- `AUTO_CREATE_SCHEMA=false`: o esquema é só do alembic.

Frontend em container (opcional):

```bash
docker compose --profile web up -d --build     # http://127.0.0.1:3000
```

O serviço `web` usa `FX_API_URL=http://api:8000` (rede interna do compose) e `FX_API_KEY` do `.env`
(vazia = reutiliza `API_KEY`). Requer `output: "standalone"` em `next.config.ts` — ver `Dockerfile.web`.
Ele publica só em `WEB_BIND=127.0.0.1` e por isso sobe com `FX_FRONTEND_PROTECTED=1`; ao publicar em outra
interface, defina `FX_BASIC_AUTH=usuario:senha` e `FX_FRONTEND_PROTECTED=0` (ver "Frontend na Vercel").

Parar e limpar:

```bash
docker compose down          # mantém volumes (dados e evidências)
docker compose down -v       # APAGA pgdata e evidence; faça backup antes
```

## Variáveis de ambiente

A lista completa, com comentários e padrões, está em `.env.example` (espelha
`backend/src/fronteira_fx/config.py`). As que decidem o deploy:

| Variável | Onde | Obrigatória | Uso |
|---|---|---|---|
| `POSTGRES_PASSWORD` | compose (`.env`) | sim | senha do Postgres; vira `DATABASE_URL` da api e do worker |
| `API_KEY` | compose → api/worker | sim | protege `/mcp` e as rotas de escrita (`X-API-Key`/Bearer) |
| `DATA_MODE` | api/worker | não (`real`) | `real` \| `simulation` \| `demo`; os modos nunca se misturam |
| `EVIDENCE_DIR` | api/worker | não | `/app/var/evidence` no compose (volume `evidence`); `FX_EVIDENCE_DIR` é alias legado |
| `TELEGRAM_BOT_TOKEN`, `SMTP_*` | api/worker | não | canais de alerta; vazio = desligado |
| `FX_API_URL` | frontend (servidor) | sim na Vercel | URL da API usada pelo proxy; no compose é fixa `http://api:8000` |
| `FX_API_KEY` | frontend (servidor) | sim na Vercel | chave que o proxy injeta; no compose cai em `API_KEY` |
| `NEXT_PUBLIC_API_URL` | frontend (navegador) | não | só dev local sem chave (chamada direta); deixe vazia com o proxy |
| `FX_BASIC_AUTH` | frontend (servidor) | não | `usuario:senha`: todo o app pede Basic Auth; habilita a chave no proxy |
| `FX_FRONTEND_PROTECTED` | frontend (servidor) | não (`1` no compose) | `1` = o frontend já é privado (loopback/VPN/Deployment Protection); habilita a chave no proxy |
| `API_BIND`, `API_PORT`, `WEB_BIND`, `WEB_PORT`, `POSTGRES_PORT` | compose | não | portas publicadas no host (padrão loopback) |
| `FORWARDED_ALLOW_IPS` | api | não | IPs de proxy reverso cujos `X-Forwarded-*` o uvicorn aceita; um proxy no host chega pelo gateway da bridge, não por `127.0.0.1` |

Regras:

- Nada com `NEXT_PUBLIC_` recebe segredo: tudo com esse prefixo é embutido no bundle do navegador.
- Portas e booleanos (`SMTP_PORT`, `SMTP_STARTTLS`) sempre com valor; strings opcionais podem ficar vazias.
- O `.env` de `fronteira-fx/` é lido pelo compose e pelo Next.js em `pnpm dev`; o backend rodado fora do
  compose (`uv run uvicorn`) lê `backend/.env`.

## Frontend: proxy server-side para a API

- Rota `src/app/api/fx/[...path]/route.ts` (Next.js, servidor): recebe `/api/fx/v1/<caminho>`, repassa para
  `${FX_API_URL}/v1/<caminho>` e devolve a resposta (inclusive o stream SSE de `/v1/stream`). Só `/v1` passa:
  `/mcp`, `/docs` e `/openapi.json` dão 404, e segmentos `.`/`..` (mesmo codificados) ou com barra dão 400.
- `X-API-Key: ${FX_API_KEY}` só é injetada com o frontend protegido: `FX_BASIC_AUTH=usuario:senha` (o app
  inteiro pede Basic Auth via `src/proxy.ts` e o proxy confere as credenciais) ou `FX_FRONTEND_PROTECTED=1`
  (o operador garante que o frontend já é privado). Sem proteção, leituras seguem sem chave e mutações
  recebem 403. Mutações de outra origem (`Sec-Fetch-Site`/`Origin`) recebem 403 sempre (CSRF).
- Em desenvolvimento: `FX_API_URL=http://localhost:8000`, `FX_API_KEY` igual à `API_KEY` do backend e
  `FX_FRONTEND_PROTECTED=1` (só se `pnpm dev` não estiver exposto na rede), no `.env` de `fronteira-fx/`.
- Como a origem vista pelo backend é sempre o servidor do Next, `CORS_ORIGINS` não precisa listar
  domínios de preview da Vercel.
- `NEXT_PUBLIC_API_URL` continua existindo apenas para dev local sem chave (chamada direta do
  navegador). Deixe-a vazia: o cliente usa o proxy `/api/fx`. Sem API alcançável, o app mostra a faixa
  "Demonstração — dados ilustrativos" e nunca mistura dados de demonstração com reais.

## Backup e restauração

Os scripts ficam em `backend/scripts/`. Sem `DATABASE_URL` eles chamam `docker compose exec`, que
localiza o projeto pela pasta atual: execute-os a partir de `fronteira-fx/` (onde está o
`docker-compose.yml`) ou exporte `COMPOSE_FILE=/caminho/para/fronteira-fx/docker-compose.yml` (útil no
cron). Com `DATABASE_URL` definida, usam `pg_dump`/`pg_restore` locais e a pasta atual não importa:

```bash
cd fronteira-fx
backend/scripts/backup.sh                 # grava ./backups/fx-<UTC>.dump (pg_dump --format=custom)
backend/scripts/backup.sh /caminho/seguro # outra pasta de saída
backend/scripts/restore.sh backups/fx-20260101T120000Z.dump   # DESTRÓI os dados atuais (--clean)
```

- Sem `DATABASE_URL` no ambiente, os scripts usam `docker compose exec -T postgres`; com
  `DATABASE_URL` (ex.: Postgres gerido), usam `pg_dump`/`pg_restore` locais.
- `backups/` e `*.dump` estão no `.gitignore`: nunca versionar dumps.
- Volumes nomeados: `fronteira-fx_pgdata` (banco) e `fronteira-fx_evidence` (screenshots/HTML dos
  adaptadores, montado em `api` e `worker`). Para copiar evidências:
  `docker compose cp worker:/app/var/evidence ./evidence-copia`.
- Teste a restauração periodicamente em um compose vazio (`docker compose down -v && up -d`, depois
  `restore.sh`); backup que nunca foi restaurado não é backup.
- Após restaurar, `docker compose restart api worker` (as migrações rodam de novo no arranque da api).

## Frontend na Vercel

O app Next.js fica em `fronteira-fx/` dentro do repositório. Ao vincular o projeto na Vercel, defina
**Root Directory = `fronteira-fx`** (a CLI faz isso automaticamente quando executada de dentro da pasta).
`vercel.json` já fixa `pnpm install --frozen-lockfile` e `pnpm build`.

```bash
cd fronteira-fx
pnpm install --frozen-lockfile
pnpm exec vercel login                 # abre o fluxo de login (navegador/dispositivo)
pnpm exec vercel deploy --yes          # prévia (Preview)
pnpm exec vercel inspect <URL> --wait  # aguarda e confere o estado
pnpm exec vercel deploy --prod --yes   # produção, após validar a prévia
```

Variáveis do projeto na Vercel (Settings → Environment Variables), definidas separadamente para
Preview e Production e **sem** o prefixo `NEXT_PUBLIC_`:

| Variável | Valor |
|---|---|
| `FX_API_URL` | URL pública HTTPS da API (ex.: `https://api.seu-dominio.tld`) |
| `FX_API_KEY` | a mesma `API_KEY` do backend; marque como *Sensitive* |
| `ENABLE_EXPERIMENTAL_COREPACK` | `1`, para a Vercel usar o pnpm fixado em `packageManager` (10.28.0) |
| `FX_BASIC_AUTH` | `usuario:senha` forte: todo o app pede Basic Auth (`src/proxy.ts`); marque como *Sensitive* |
| `FX_FRONTEND_PROTECTED` | `1` **só** se o projeto tiver Vercel Deployment Protection (ou outra barreira) cobrindo Preview e Production |

**O frontend público precisa de proteção.** O proxy `/api/fx` injeta `FX_API_KEY`, então quem alcança o
frontend faz as escritas com a chave. Por isso o proxy só injeta a chave quando `FX_BASIC_AUTH` está definido
(e a requisição traz as credenciais) ou quando `FX_FRONTEND_PROTECTED=1`; sem nenhum dos dois, leituras seguem
sem chave e mutações recebem `403`. Além disso o proxy só repassa `/v1/...` (nunca `/mcp`, `/docs` ou
`/openapi.json`), recusa segmentos `.`/`..` (mesmo codificados) e recusa mutações de outra origem
(`Sec-Fetch-Site`/`Origin`).

Deixe `NEXT_PUBLIC_API_URL` **vazia** na Vercel: com o proxy, o navegador não precisa (e não deve)
conhecer a API.

Prévia sem login: `pnpm exec vercel deploy --temporary --yes` publica uma prévia anônima que expira em
60 minutos e devolve uma `claimUrl`; abri-la logado transfere o deployment para a sua conta.

Stream em tempo real: `/v1/stream` (SSE) é servido pelo backend e repassado pelo proxy. O servidor
limita cada conexão (`STREAM_MAX_DURATION_S`, padrão 55 s) e o cliente reconecta por cursor
(`Last-Event-ID`), com fallback de snapshot; confira que o limite de duração de funções do seu plano
Vercel é maior que esse valor. Cursor expirado (HTTP 410) força novo snapshot.

## Modo grátis: API na Vercel e coleta disparada pelo Supabase

Esta é uma alternativa ao host durável da seção seguinte. A API roda como **função da Vercel** (plano
Hobby, sem custo) e a coleta é disparada de fora: o `pg_cron` do Supabase chama
`POST /v1/internal/collect` a cada 5 minutos. Não há processo residente, nem worker, nem navegador.

Como fica a divisão:

| Peça | Onde roda |
|---|---|
| Banco (Postgres + pgvector) | Supabase (pooler em modo transação, porta 6543) |
| API (`/v1/*`, SSE, `/v1/internal/collect`) | função Python na Vercel, projeto com raiz em `fronteira-fx/backend` |
| Coleta | o endpoint acima, uma volta por chamada, com orçamento de 45 s |
| Agendador | `pg_cron` + `pg_net` no Supabase |
| Frontend | Vercel, como na seção "Frontend na Vercel" |

**Fontes com navegador** (hoje só a **Western Union**, `westernunion`) rodam neste modo apenas com o
**mini navegador** (subseção abaixo). Sem ele, aparecem em `skipped` com o motivo "requer navegador". As
demais fontes são HTML ou API oficial e rodam normalmente.

**Como o SSE muda.** Em função, cada conexão de `/v1/stream` dura no máximo 4 s (`STREAM_MAX_DURATION_S=4`)
e o `retry:` do servidor manda o navegador reconectar só depois de 30 s (`STREAM_RETRY_MS=30000`). Na
prática o SSE vira uma consulta a cada ~30 s: barato em função, mas uma mudança de cotação chega à tela com
até uns 35 s de atraso. Quem usa o app com a aba aberta gera uma invocação a cada ~30 s; ver os números abaixo.

### Variáveis da função (Vercel → Settings → Environment Variables)

Sem o prefixo `NEXT_PUBLIC_`. Marque `DATABASE_URL`, `API_KEY` e `CRON_SECRET` como *Sensitive*.

| Variável | Valor | Por quê |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://postgres.<project-ref>:<senha>@aws-0-<regiao>.pooler.supabase.com:6543/postgres?sslmode=require` | pooler em modo transação (porta 6543); `sslmode=require` obrigatório |
| `FX_SERVERLESS` | `1` | liga `NullPool` e `prepare_threshold=None` (o pooler de transação não aceita comandos preparados) |
| `AUTO_CREATE_SCHEMA` | `0` | o esquema vem do alembic, rodado de fora (ver "Primeira rodada") |
| `SEED_KNOWLEDGE` | `0` | a base de conhecimento já está no banco; não reindexar a cada partida a frio |
| `DATA_MODE` | `real` | a função nunca serve demonstração |
| `API_KEY` | `<API_KEY>` (`openssl rand -hex 32`) | protege `/mcp` e as rotas de escrita |
| `CRON_SECRET` | `<CRON_SECRET>` (`openssl rand -hex 32`) | o Bearer que o Supabase manda; vazio = a rota responde 404 |
| `CORS_ORIGINS` | `https://<frontend>.vercel.app` | origem do frontend; o proxy server-side já cobre o uso normal |
| `STREAM_MAX_DURATION_S` | `4` | cada conexão SSE dura 4 s; ver acima |
| `STREAM_RETRY_MS` | `30000` | o `retry:` do SSE: o cliente reconecta a cada 30 s |
| `COLLECT_BUDGET_S` | `45` (padrão) | nenhuma fonte nova começa depois de 45 s; a função tem 60 s |
| `EVIDENCE_DIR` | `/tmp/evidence` (recomendado) | o disco da função é somente leitura, exceto `/tmp`; as capturas brutas são efêmeras e os dados ficam no banco |

Sem `FX_SERVERLESS=1`, a conexão em modo transação falha depois de algumas execuções (os comandos
preparados do `psycopg`). Não troque a porta 6543 sem essa variável.

### Primeira rodada

1. No SQL Editor do Supabase: `CREATE EXTENSION IF NOT EXISTS vector;` (o mesmo passo da seção do Supabase).
2. Rode as migrações **de fora da Vercel**, pela porta de sessão 5432 (migrações não cabem no modo transação):

   ```bash
   cd backend
   DATABASE_URL='postgresql+psycopg://postgres.<project-ref>:<senha>@aws-0-<regiao>.pooler.supabase.com:5432/postgres?sslmode=require' \
     uv run alembic upgrade head
   ```

3. Vincule o projeto da Vercel com **Root Directory = `fronteira-fx/backend`** e cadastre as variáveis acima.
   O `vercel.json` desta pasta fixa a região `gru1` (São Paulo) e `maxDuration` de 60 s para `app.py`.
   O `app.py` expõe a `app` do FastAPI e coloca `src/` no caminho de importação.
4. Confira: `curl -fsS https://<API_VERCEL>/v1/health` deve responder `data_mode: "real"`.

### Agendador no Supabase (modelo)

Use os marcadores no lugar dos valores. O segredo fica no **Vault** do Supabase, não em arquivo nem no
comando do agendamento: o comando lê o Vault na hora de disparar.

```sql
-- 1. Extensões (uma vez, no SQL Editor)
CREATE EXTENSION IF NOT EXISTS pg_cron;
CREATE EXTENSION IF NOT EXISTS pg_net;

-- 2. Segredo no Vault: troque <CRON_SECRET> pelo mesmo valor da variável da Vercel
select vault.create_secret('<CRON_SECRET>', 'fx_cron_secret', 'Bearer de /v1/internal/collect');

-- 3. Agendamento a cada 5 minutos
select cron.schedule(
  'fx-collect',
  '*/5 * * * *',
  $$
  select net.http_post(
    url := 'https://<API_VERCEL>/v1/internal/collect',
    headers := jsonb_build_object(
      'Authorization', 'Bearer ' || (select decrypted_secret from vault.decrypted_secrets where name = 'fx_cron_secret'),
      'Content-Type', 'application/json'
    ),
    body := '{}'::jsonb,
    timeout_milliseconds := 55000
  );
  $$
);
```

- `<API_VERCEL>` é o domínio da função (ex.: `<projeto>.vercel.app`), sem barra no fim.
- `net.http_post` é assíncrono: a resposta fica em `net._http_response` (código HTTP e corpo). Para ver se a
  rodada deu certo, consulte essa tabela; o corpo traz só o resumo do endpoint, sem segredo.
- Para trocar o segredo: `select vault.update_secret(...)` com o novo valor e a mesma variável na Vercel.
- Para parar: `select cron.unschedule('fx-collect');`.

### Limites do plano Hobby e por que 5 minutos

Números do plano Hobby da Vercel, como informados ao projeto:

- 4 horas de CPU ativa por mês;
- 360 GB-hora de memória por mês;
- 1 milhão de invocações por mês.

Estourar um limite **pausa as funções por 30 dias**. Confira o consumo no painel de uso da Vercel depois
do primeiro dia.

Por que 5 minutos:

- o intervalo padrão de sondagem de uma fonte já é 300 s (`POLL_INTERVAL_S`); chamar a cada 5 minutos
  acompanha o agendamento real, e uma chamada mais frequente quase só encontra fontes "não vencidas";
- cada chamada gasta CPU ativa (importar o app, consultas, parse). Na conta: 5 minutos são 8.640 chamadas
  por mês, ~0,9% do limite de invocações, mas o limite de CPU de 4 h dá **~1,7 s de CPU por chamada**.
  Esse é o ponto apertado. Se o painel mostrar consumo alto de CPU, troque o agendamento por
  `*/10 * * * *` (ou mais lento): `select cron.unschedule('fx-collect');` e de novo `cron.schedule(...)` com o novo intervalo;
- o SSE de quem deixa o app aberto soma invocações: uma a cada ~30 s por aba, ~86 mil por mês para uma
  aba 24 horas por dia. Com o limite de 1 milhão, isso comporta poucas abas abertas o mês inteiro.

Os números de CPU são uma estimativa de projeto, não uma medição: meça no primeiro mês antes de confiar.

### Verificação

```bash
# sem segredo configurado: a rota não existe (404)
curl -sS -o /dev/null -w '%{http_code}\n' -X POST https://<API_VERCEL>/v1/internal/collect
# segredo errado: 401
curl -sS -o /dev/null -w '%{http_code}\n' -X POST -H 'Authorization: Bearer <SEGREDO_ERRADO>' https://<API_VERCEL>/v1/internal/collect
# segredo certo: 200 com o resumo da rodada
curl -sS -X POST -H "Authorization: Bearer <CRON_SECRET>" https://<API_VERCEL>/v1/internal/collect
```

Use `<CRON_SECRET>` só no seu terminal e nunca cole a resposta de produção num arquivo versionado.

### O que não está garantido nesta seção

- Não foi medido em produção: consumo real de CPU, tempo de cold start e o limite de 4 s do SSE na Vercel.
- O `pg_net` pode atrasar a chamada alguns segundos; o orçamento de 45 s conta só o trabalho da função.
- Uma função morta pelo limite de 60 s deixa tarefas em `running`, como já acontece com o worker se ele cair
  no meio de uma tarefa. Não há recuperação automática nesta versão.

### Mini navegador na Vercel

A Western Union só tem cotação depois de um fluxo de cliques (o preço vem de uma chamada com fingerprint do
navegador). Para rodar isso de graça, `fronteira-fx/browser/` é um projeto Vercel separado: uma função
`POST /api/westernunion` roda o mesmo fluxo num Chromium sem tela e devolve o `scenario` que o adaptador
Python lê. Detalhes e testes locais: `fronteira-fx/browser/README.md`.

1. Crie outro projeto na Vercel com **Root Directory = `fronteira-fx/browser`**, região `gru1` (já em
   `vercel.json`), e defina `BROWSER_SECRET` (*Sensitive*, `openssl rand -hex 32`).
2. No backend (api e worker), defina as variáveis abaixo com o **mesmo** segredo e a URL pública do projeto.
   Sem as duas, o backend continua abrindo o Chromium local (extra `browser`), como antes.

| Variável | Valor |
|---|---|
| `FX_BROWSER_URL` | URL https do projeto do mini navegador (ex.: `https://fx-browser.seu-dominio.tld`); http só para localhost |
| `FX_BROWSER_SECRET` | o mesmo `BROWSER_SECRET` da Vercel; marque como *Sensitive*; nunca em arquivo versionado |
| `REMOTE_BROWSER_MIN_INTERVAL_S` | opcional; padrão `7200` (no máximo uma consulta remota por fonte a cada 2 h) |

Com as duas primeiras definidas: o adaptador da Western Union chama `POST {FX_BROWSER_URL}/api/westernunion`
(timeout de 130 s, Bearer) e grava a captura como evidência; `blocked` e `degraded` viram o status
correspondente; falha de rede, `401`, `404` ou JSON inválido viram `error`, sem exceção. Pedidos sob demanda
dessa fonte rodam direto, sem a fila do worker, e respeitam o intervalo mínimo.

Custo: cada execução gasta segundos de CPU. No plano grátis da Vercel há cerca de 4 horas de CPU por mês;
mantenha o intervalo de 2 h. O segredo fica só em variáveis de ambiente: o backend recusa o placeholder
`TROQUE_*` e URL que não seja https (exceto localhost).

### Vigia de mudanças no Supabase (coleta ao vivo grátis)

Problema: a API na Vercel tem 4 horas de CPU por mês, e coletar todas as fontes a cada minuto gastaria ~16 h
(cada fonte custa ~0,13 s de CPU). Solução: o próprio Postgres do Supabase **vigia** as fontes e só chama a
Vercel quando algo mudou. Arquivo: `fronteira-fx/deploy/supabase/vigia.sql` (idempotente, sem segredos).

**Como funciona.** A cada 30 s, `fx_watch_tick()` roda no `pg_cron`:

1. lê as respostas dos pedidos enviados antes (`net._http_response`); para 2xx, calcula a impressão digital da
   página (md5 dos números: `6.085`, `1.110`, `5,4935`, `7350`) e, se mudou, marca a fonte como mudada; grava o
   `last_status`; pedido sem resposta há mais de 2 min é descartado;
2. junta as fontes mudadas que ainda não foram enviadas à API e faz **um** `POST /v1/internal/collect` com
   `{"sources": [...]}` e o Bearer do Vault. Fonte volátil (preço de mercado) entra no máximo a cada 5 min;
3. dispara um `GET` (ou `POST`) para cada fonte cujo último pedido passou de `min_interval_s` (60 s).

A API então coleta só as fontes da lista, com agendamento forçado e o piso de 60 s (ver
`docs/api-contract.md`, seção `internal`). A primeira leitura de cada fonte conta como mudança: depois de ligar,
cada fonte chama a API uma vez.

**Custos.** A CPU da Vercel só é gasta quando uma fonte muda (mais o custo da própria chamada). Não há
processo residente. O consumo real ainda não foi medido em produção: meça no painel da Vercel na primeira
semana.

**Politeza.** Cada fonte recebe no máximo **1 requisição por minuto do vigia** (pelo `min_interval_s`), e a API
faz no máximo **1 busca extra** quando a fonte muda (piso de 60 s). O timeout de cada requisição é 20 s. Isso é
mais frequente que os 300 s de sondagem do adaptador hoje (`POLL_INTERVAL_S`): é o pedido de vigiar a cada minuto.
Se algum site reclamar ou começar a bloquear, aumente `min_interval_s` da fonte (mínimo 60) em vez de desligar tudo.

**Alvos.** Um por fonte do registro, exceto a Western Union. Uma URL por fonte (o que o adaptador consulta de
fato, com os mesmos cabeçalhos do `fetch`):

| Fonte | Método | Volátil | Intervalo | Observação |
|---|---|---|---|---|
| `alberdi` | GET | não | 60 s | JSON `ws/getTablero.json.php` |
| `bonanza` | GET | não | 60 s | JSON `api/board` |
| `bcp` | GET | não | 300 s | Feed Frankfurter, só USD; referencial diário |
| `chaco` | GET | não | 60 s | JSON `api/branch_office/1/exchange`: **uma filial** (Casa Central) |
| `dolarpy` | GET | sim | 60 s | Agregador de mercado (`dolar.melizeche.com/api/1.0/`) |
| `maxicambios` | GET | não | 60 s | HTML da home |
| `myd` | GET | não | 60 s | HTML da home |
| `nomad` | GET | sim | 60 s | JSON `exchanges:90-days` |
| `norte` | GET | não | 60 s | HTML da home: **só a filial padrão** (as outras pedem POST do Livewire) |
| `revolut` | GET | sim | 60 s | `quote` USD→BRL com os parâmetros padrão (1000 USD, BR, pt-BR) |

**O que não cobre.**

- Western Union: precisa de navegador; fica de fora do vigia (segue na coleta do worker ou do mini navegador).
- Chaco e Norte: o vigia olha uma filial. Mudança só em outra filial aparece na próxima rodada de agendamento
  (ver abaixo), não no vigia.
- Quem muda só texto, sem números que a regex pega, não dispara a API.
- Inteiro colado em letra (`PYG7350`, sem espaço) não conta; decimal colado conta (`USD6.085`).
- Números aleatórios de página (tokens CSRF) já são ignorados, mas uma página nova com outro tipo de ruído
  numérico pode gerar chamadas à API sem mudança de cotação. Confira `last_status` e o consumo da Vercel.
- Revolut bloqueia clientes que não são navegador: o alvo pode voltar `403` (aparece em `last_status`), e então
  o vigia não detecta nada para ela.
- Não foi medido em produção: quantas chamadas por dia, quanto de CPU, e se os sites respondem bem a 1 requisição
  por minuto.

**Ligar.** Pré-requisitos: as extensões `pg_net` e `pg_cron` (passo 1 da seção anterior) e o segredo `fx_cron_secret`
no Vault (passo 2 da seção anterior, o mesmo Bearer da Vercel).

```sql
-- 1. Rode o arquivo inteiro no SQL Editor (cria tabelas, função e alvos; pode repetir sem problema)
--    deploy/supabase/vigia.sql
-- 2. A URL da API, sem barra no fim (o domínio da função Vercel)
insert into public.fx_watch_config (key, value) values ('api_url', 'https://<API_VERCEL>')
  on conflict (key) do update set value = excluded.value;
-- 3. Agendamento a cada 30 s
select cron.schedule('fx-vigia', '30 seconds', 'select public.fx_watch_tick()');
```

**Desligar.** `select cron.unschedule('fx-vigia');` para parar as leituras. Apagar a linha `api_url` para
parar só as chamadas à API (o vigia segue lendo as fontes e marca as mudanças como pendentes).

**Agendamento de 5 minutos (`fx-collect`).** Com o vigia ligado, a rodada de 5 minutos da seção anterior custa
~1,7 s de CPU por chamada e sozinha consome o plano grátis. Recomendação: `select cron.unschedule('fx-collect');`
depois de confirmar que o vigia chama a API, ou troque por `*/30 * * * *` como rede de segurança (a decisão é de quem
opera).

**Testes.** `backend/tests/test_vigia_sql.py` (paridade com o backend: user-agent, um alvo por adaptador, sem
segredo no arquivo) e `deploy/supabase/tests/fingerprint_check.sql` (impressão digital, rodar com `psql` depois
do `vigia.sql`). O comportamento da função (mudança, volátil com 5 min, pedido órfão, HTTP 500, configuração
ausente, payload do POST, agendamento) foi testado contra Postgres com `pg_net` e `pg_cron` da imagem
`supabase/postgres`, com um servidor de teste local.

## Coletor ao vivo na Oracle Cloud (Always Free)

No modo grátis da Vercel a coleta roda a cada 5 minutos: consultar cada fonte a cada minuto gastaria umas 16 horas de
CPU por mês (medido: ~0,13 s por fonte), e o plano Hobby tem 4. Para a coleta ao vivo (cada fonte a cada 60 s, o
piso do projeto, e a Western Union com Chromium local), o **worker** roda numa VM Always Free da Oracle. O site e a API
continuam na Vercel e o banco no Supabase; a VM não abre nenhuma porta de entrada.

| Peça | Onde |
|---|---|
| Worker (coleta a cada 60 s, Western Union com navegador, fila de tarefas) | VM Oracle, `deploy/oracle/compose.yml` |
| Banco | Supabase, pooler em modo sessão (porta 5432) com o papel `fx_worker` |
| API e site | Vercel (sem mudança) |
| Agendador do Supabase | continua a cada 5 min como reserva: o estado de sondagem é o mesmo (`watch_states`, com trava de linha), então nada é consultado em dobro |

**Papel do banco.** O worker usa o papel `fx_worker` (login próprio, sem DDL, com política de linha `fx_worker_all` em
cada tabela, porque o RLS está ligado). Trocar a senha não mexe na Vercel. Migração nova que cria tabela precisa da
política também (`create policy fx_worker_all on public.<tabela> for all to fx_worker using (true) with check (true)`).

**Instalação.**
1. Crie a conta Always Free da Oracle com região inicial **Brazil East (São Paulo)**.
2. Compute → Instances → Create instance: imagem **Canonical Ubuntu 24.04**; forma **VM.Standard.A1.Flex** (1 OCPU,
   6 GB; se faltar capacidade, **VM.Standard.E2.1.Micro**, que ganha 2 GB de swap no setup); rede padrão com IP público.
3. Em *Advanced options → Management → cloud-init script*, cole o `deploy/oracle/cloud-init.example.yaml` preenchido
   (senha do `fx_worker` e o ref do projeto). Crie a instância.
4. O cloud-init instala Docker e git, clona a branch só com `fronteira-fx/`, grava `/etc/fronteira-fx/worker.env`
   (600, root), sobe o worker e liga o timer `fronteira-fx-update` (a cada 5 min: se a branch mudou, reconstrói e
   reinicia). Quem pode enviar commits para a branch controla o que roda na VM.

**Variáveis do worker** (`/etc/fronteira-fx/worker.env`): `DATABASE_URL` (fx_worker, porta 5432, `sslmode=require`),
`DATA_MODE=real`, `AUTO_CREATE_SCHEMA=0`, `SEED_KNOWLEDGE=0`, `SEED_DEMO=0`, `EVIDENCE_DIR=/app/var/evidence`,
`WORKER_TICK_S=10`, `POLL_INTERVAL_S=60`, `WATCH_MAX_INTERVAL_S=180`. Sem `FX_SERVERLESS` (o worker usa pool normal).

**Verificação.** No Supabase: `select count(*) from pg_stat_activity where usename = 'fx_worker';` maior que zero e
cotações novas a cada minuto. Na VM (se precisar): `journalctl -u fronteira-fx-update` e
`docker compose -f /opt/fronteira-fx/fronteira-fx/deploy/oracle/compose.yml logs -f worker`.

## Backend e worker em um host durável

Vercel Functions não hospedam o coletor nem processos indefinidos. `api` e `worker` vão para uma VPS
(ou Fly.io/Railway/Render com suporte a Docker Compose ou a imagens equivalentes):

1. Docker Engine + Compose v2 no host; clone o repositório e siga "Subida local" acima.
2. Mantenha `API_BIND=127.0.0.1`. Ponha um proxy reverso com TLS (Caddy, nginx, Traefik) escutando em
   `:443` e encaminhando para `127.0.0.1:8000`; é essa URL HTTPS que vai em `FX_API_URL` na Vercel.
   Dentro do container o proxy aparece com o IP do gateway da bridge do Docker (ex.: `172.18.0.1`; veja
   `docker network inspect fronteira-fx_default`), nunca `127.0.0.1`: defina `FORWARDED_ALLOW_IPS` no
   `.env` com esse IP (ou `*`, aceitável só enquanto `API_BIND` ficar em loopback) para o uvicorn
   honrar `X-Forwarded-Proto`/`X-Forwarded-For`.
3. Firewall: só `22`, `80` e `443` abertos. O Postgres nunca sai do loopback.
4. O worker precisa de `shm_size: 1gb` (Chromium) e de disco para `evidence`; o Postgres, de disco para
   `pgdata`. Monitore com `docker compose ps` e `docker compose logs`.
5. Atualização: `git pull && docker compose up -d --build` (as migrações rodam no arranque da api; o
   worker espera a api saudável). Rotacione logs do Docker (`log-opts` em `/etc/docker/daemon.json`).
6. Backup agendado (cron) com `backend/scripts/backup.sh` para um destino fora do host.

Nunca desabilite verificação TLS nos adaptadores nem configure `HTTPS_PROXY` nos containers para
contornar bloqueios: o coletor respeita o piso de 60 s por fonte e recua após erro.

## Imagens pinadas por digest

Todas as bases são fixadas por tag **e** digest; renovar é uma troca consciente, não um efeito do
`docker compose pull`.

| Imagem | Versão | Acoplada a |
|---|---|---|
| `ghcr.io/astral-sh/uv:0.11.32-python3.13-trixie-slim` | uv 0.11.32 | `uv_build` em `backend/pyproject.toml` |
| `ghcr.io/astral-sh/uv:0.11.32` (só o binário, no worker) | uv 0.11.32 | idem |
| `mcr.microsoft.com/playwright/python:v1.64.1-noble` | Playwright 1.64.1 | `playwright` em `backend/uv.lock` (versões têm de coincidir) |
| `pgvector/pgvector:0.8.7-pg16` | pgvector 0.8.7 / PG 16 | formato do volume `pgdata` (trocar o major do PG exige dump/restore) |
| `node:22.23.4-bookworm-slim` | Node 22 | `engines.node` em `package.json` |

Para atualizar um pin, obtenha o digest novo e substitua tag e digest juntos:

```bash
docker buildx imagetools inspect ghcr.io/astral-sh/uv:<versão>-python3.13-trixie-slim
docker buildx imagetools inspect mcr.microsoft.com/playwright/python:v<versão>-noble
docker buildx imagetools inspect docker.io/pgvector/pgvector:<versão>-pg16
docker buildx imagetools inspect docker.io/library/node:<versão>-bookworm-slim
```

Ao subir o Playwright, mude `uv.lock` (`uv lock --upgrade-package playwright`) e a tag da imagem na
mesma alteração.

## O que foi verificado nas imagens Docker (2026-11-04)

Verificação feita em 2026-11-04 num contêiner Linux de desenvolvimento, com Docker Engine 29.9.2
(overlayfs, daemon sem bridge e sem iptables, `--network=host` nos builds e nos containers). Não é
prova de produção: serve para saber o que já foi exercitado e o que não foi.

Verificado:

- `docker compose config -q` passa com as variáveis de `.env.example` e **falha** sem
  `POSTGRES_PASSWORD` ou `API_KEY` (o `:?` funciona).
- Subida da pilha completa (postgres, api, worker e web, com `--profile web`) com um override temporário
  de rede (`network_mode: host`, fora do Git) e imagens de teste construídas a partir dos Dockerfiles
  (ver o ponto de builds abaixo): `postgres` fica `healthy`; `api` roda as migrações do alembic
  e fica `healthy`; `worker` sobe; `web` fica `healthy`. `pgvector` está disponível no banco.
- Em `DATA_MODE=demo`: `GET /v1/health`, `GET /v1/candles` e `GET /v1/pregao/sessions` respondem;
  `/mcp` sem chave responde 401; `/pregao` responde 200 pelo frontend; `/api/fx/v1/health` responde 200
  pelo proxy server-side.
- Worker: a imagem importa `fronteira_fx` e o Playwright 1.64.1, lança o Chromium headless e o laço de
  coleta roda ticks; em `demo` ele não consulta provedores. Um `SIGTERM` encerra com código 0.
- Frontend com `FX_BASIC_AUTH` definido: o `HEALTHCHECK` original (que exigia `2xx` na raiz) ficava
  `unhealthy`, porque o proxy responde 401 sem credenciais. Corrigido em `Dockerfile.web` para aceitar
  qualquer resposta abaixo de 500 (o servidor está de pé); verificado depois da correção: `healthy`.

Não verificado (e por isso não prometido):

- Os três `docker build` oficiais (`backend/Dockerfile`, `backend/Dockerfile.worker`, `Dockerfile.web`)
  **não concluíram neste ambiente**: o proxy de saída do sandbox re-cifra o HTTPS com uma CA que não
  está no trust store dos contêineres, e `uv`/`npm` falham com `UnknownIssuer`/`SELF_SIGNED_CERT_IN_CHAIN`
  ao baixar de `files.pythonhosted.org` e `registry.npmjs.org`. É um problema do sandbox, não do
  Dockerfile. As imagens usadas nos testes acima vieram de cópias dos Dockerfiles com a CA do proxy
  injetada (só para teste, fora do Git). Confirme os builds oficiais num runner sem proxy interceptador
  (a CI, job `docker`, já faz isso).
- Coleta contra provedores reais (`DATA_MODE=real`), notificações, backup e restauração, publicação do
  frontend na Vercel e o `HEALTHCHECK` de longa duração em produção.

## Supabase como Postgres gerenciado (opcional)

1. **Enquadramento.** O Supabase entra **somente** como Postgres gerenciado com pgvector. O backend
   continua falando SQLAlchemy + `psycopg` 3, o mesmo driver de hoje (`postgresql+psycopg://`). Nenhum
   SDK, Auth, Storage ou Edge Function do Supabase é usado, e o frontend não conhece o banco.

2. **Como `DATABASE_URL` é lida.** Em `backend/src/fronteira_fx/config.py`, `Settings` é
   `pydantic-settings` com `env_file=".env"` (caminho relativo ao diretório de execução: rode os
   comandos a partir de `backend/`) e `extra="ignore"`. O modelo `backend/.env.example` (só placeholders,
   nenhum valor real) fica rastreado de propósito: o `.gitignore` ignora `.env*` mas libera
   `!.env.example`, então este modelo e o `.env.example` da raiz do projeto entram no Git sem `-f`.
   Copie-o para `backend/.env`, que nunca entra no Git. O campo `database_url: str` (padrão
   `sqlite:///./var/fx.db`) vem da variável `DATABASE_URL`. `auto_create_schema: bool = True` vem de
   `AUTO_CREATE_SCHEMA`. `is_sqlite` é `database_url.startswith("sqlite")`. O `alembic/env.py` lê o
   mesmo `get_settings().database_url`. O `docker-compose.yml` já monta
   `postgresql+psycopg://…@postgres:5432/…`; a mesma forma vale para o Supabase.

3. **Conexão.** Use o **pooler em modo sessão, porta 5432** (`aws-0-<regiao>.pooler.supabase.com`,
   usuário `postgres.<project-ref>`) para API, worker e Alembic, sempre com `?sslmode=require`.

   **Por que não o modo transação (porta 6543).** O `psycopg` 3 cria comandos preparados no servidor a
   partir da 5ª execução, e o pooler em modo transação não os suporta. Habilitar o modo transação
   exigiria `connect_args={"prepare_threshold": None}` no `create_engine`, uma mudança de código fora
   desta seção, registrada como pendência em `docs/pregao.md` (seção "Pendências"). Essa mudança já existe
   para o modo serverless (`FX_SERVERLESS=1`, ver "Modo grátis" abaixo), que usa o pooler em modo transação
   (porta 6543). Fora do serverless o modo transação continua sem suporte: use a porta 5432.

   Exemplo de URL, com placeholders:

   ```text
   postgresql+psycopg://postgres.<project-ref>:<senha>@aws-0-<regiao>.pooler.supabase.com:5432/postgres?sslmode=require
   ```

4. **Primeira configuração.** No SQL Editor do projeto, rode uma vez:

   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   ```

   No primeiro deploy, use `AUTO_CREATE_SCHEMA=true` **ou** migrações com
   `cd backend && uv run alembic upgrade head`. Regra: ambientes de produção usam Alembic e
   `AUTO_CREATE_SCHEMA=false` a partir do segundo deploy.

5. **Segredos.** `DATABASE_URL` fica só nas variáveis de ambiente do host do backend (Fly, Railway,
   Render ou VPS). Nunca em `NEXT_PUBLIC_*` e nunca no Git: o hook `pre-commit` do husky bloqueia commit
   com segredo verificado pelo TruffleHog quando o TruffleHog está disponível (binário ou Docker).
   Rotação: redefina a senha do banco no painel do Supabase, atualize a variável e reinicie API e worker.

6. **Verificação.** Com `DATABASE_URL` apontando para o Supabase no ambiente:

   ```bash
   cd backend && uv run python -c "from fronteira_fx.config import get_settings; s = get_settings(); print(s.is_sqlite, s.database_url.split('@')[-1])"
   ```

   Deve imprimir `False` e o host sem credenciais. `GET /v1/health` responde o `data_mode` do ambiente.
   Para confirmar que o JSON de horários das casas entra no wheel publicado (o comando deve imprimir uma linha; sem saída, o arquivo não foi empacotado):

   ```bash
   cd backend && uv build && unzip -l dist/*.whl | grep market_hours.json
   ```

7. **O que não fazer.** Não usar `sslmode` diferente de `require` e não desligar a verificação TLS do
   cliente. Não colar a service_role key em nenhum arquivo versionado. Não usar a conexão direta IPv6
   em hosts que só têm IPv4.

## Checklist de aceitação antes de promover para produção

- `docker compose config -q` passa com o `.env` real e falha sem ele (segredos obrigatórios).
- `docker compose up -d --build`: `postgres` e `api` ficam `healthy`; o `worker` só parte depois.
- `curl -fsS https://<api>/v1/health` responde `data_mode: real` pela URL que a Vercel usa.
- `pnpm test:all` verde (typecheck, lint, unitários, build, Playwright em 1440/1024/390 px).
- Com `FX_API_URL`/`FX_API_KEY` na Vercel, o app fala com a API real pelo proxy (`/api/fx/v1/health`
  responde `data_mode: real`); sem API alcançável, aparece a faixa "Demonstração — dados ilustrativos".
- Nenhuma variável `NEXT_PUBLIC_*` contém segredo; `.env` não está no Git (`git check-ignore .env`).
- Backup recente restaurado com sucesso em um ambiente vazio.
