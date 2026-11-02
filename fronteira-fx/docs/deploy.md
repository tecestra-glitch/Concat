# Deploy — Fronteira FX

## Frontend (Vercel)

O app Next.js fica em `fronteira-fx/` dentro do repositório. Ao vincular o projeto na Vercel, defina
**Root Directory = `fronteira-fx`** (a CLI faz isso automaticamente quando executada de dentro da pasta).

```bash
cd fronteira-fx
pnpm install --frozen-lockfile
pnpm exec vercel login                 # abre o fluxo de login (navegador/dispositivo)
pnpm exec vercel deploy --yes          # prévia (Preview)
pnpm exec vercel inspect <URL> --wait  # aguarda e confere o estado
pnpm exec vercel deploy --prod --yes   # produção, após validar a prévia
```

### Prévia sem login (deployment temporário)

`pnpm exec vercel deploy --temporary --yes` publica uma prévia anônima que **expira em 60 minutos**
e devolve uma `claimUrl`. Abrir a `claimUrl` logado na Vercel transfere o deployment para a sua conta,
que passa a mantê-lo. É o caminho usado nesta sessão por não haver autenticação da Vercel no ambiente.

### Variáveis de ambiente

| Variável | Ambiente | Uso |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | Preview e Production, separadamente | URL pública da API FastAPI. Vazia → modo demonstração isolado. |

Nunca coloque segredos em `NEXT_PUBLIC_*`: tudo com esse prefixo vai para o navegador. Chaves de
provedores, `DATABASE_URL`, `API_KEY` do MCP etc. ficam apenas no backend.

### Stream em tempo real

`/v1/stream` (SSE) é servido pelo backend, não por Vercel Functions. O cliente reconecta por cursor
(`Last-Event-ID`), fecha conexões de forma controlada (o servidor limita a duração, padrão 55 s) e
mantém fallback de snapshot a cada 30 s. Cursor expirado (HTTP 410) força novo snapshot.

## Backend e worker (containers persistentes)

Vercel Functions têm duração limitada e não hospedam coletores de navegador nem processos
indefinidos. Backend (`api`) e coletor (`worker`) são containers; veja `docs/backend.md` e
`docker-compose.yml` (PostgreSQL + pgvector, API, worker). Hosts compatíveis: Fly.io, Railway, Render,
uma VPS com Docker, etc. Exponha a API em HTTPS e aponte `NEXT_PUBLIC_API_URL` para ela.

## Supabase como Postgres gerenciado (opcional)

1. **Enquadramento.** O Supabase entra **somente** como Postgres gerenciado com pgvector. O backend
   continua falando SQLAlchemy + `psycopg` 3, o mesmo driver de hoje (`postgresql+psycopg://`). Nenhum
   SDK, Auth, Storage ou Edge Function do Supabase é usado, e o frontend não conhece o banco.

2. **Como `DATABASE_URL` é lida.** Em `backend/src/fronteira_fx/config.py`, `Settings` é
   `pydantic-settings` com `env_file=".env"` (caminho relativo ao diretório de execução: rode os
   comandos a partir de `backend/`) e `extra="ignore"`. O modelo `backend/.env.example` (só placeholders,
   nenhum valor real) fica rastreado de propósito, apesar da regra `.env*` do `.gitignore`: ele foi
   adicionado com `git add -f`; se precisar recriá-lo, faça o mesmo. Copie-o para `backend/.env`, que
   nunca entra no Git. O campo `database_url: str` (padrão
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

- `pnpm test:all` verde (typecheck, lint, unitários, build, Playwright em 1440/1024/390 px).
- Faixa "Demonstração — dados ilustrativos" visível quando a API não está configurada.
- Com API configurada: `/v1/health` responde `data_mode: real`, indicador "Conectado" no topo.
- Idade da cotação separada do estado da conexão.
