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
   desta seção, registrada como pendência em `docs/pregao.md` (seção "Pendências"). Até lá, o modo
   transação não é suportado.

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
