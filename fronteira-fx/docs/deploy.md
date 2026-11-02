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

## Checklist de aceitação antes de promover para produção

- `pnpm test:all` verde (typecheck, lint, unitários, build, Playwright em 1440/1024/390 px).
- Faixa "Demonstração — dados ilustrativos" visível quando a API não está configurada.
- Com API configurada: `/v1/health` responde `data_mode: real`, indicador "Conectado" no topo.
- Idade da cotação separada do estado da conexão.
