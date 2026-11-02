# Fronteira FX

Terminal pessoal de câmbio, remessas, cartões e oportunidades financeiras para **BRL · USD · PYG** em
Ciudad del Este, Asunción e Pedro Juan Caballero, cobrindo Western Union, ueno, Nomad, Revolut e casas de câmbio.

> Este projeto vive na pasta `fronteira-fx/` do repositório. O frontend Next.js fica aqui na raiz da pasta
> (para o deploy na Vercel use **Root Directory = `fronteira-fx`**); o backend Python fica em `backend/`.

## Estrutura

```
fronteira-fx/
├── src/                 Next.js 16 · React 19 · TypeScript · Tailwind 4 · shadcn-style UI
│   ├── app/             telas por rota: início, mercados, oportunidades, simulador, monitor, alertas, contas,
│   │                    fontes, diário, conhecimento, memória, configurações
│   │   └── api/fx/      proxy server-side para a API (injeta X-API-Key; o navegador nunca vê a chave)
│   ├── components/      shell, mercados, gráficos (Lightweight Charts), oportunidades, simulador, alertas
│   └── lib/             contrato de API (types), cliente (`/api/fx`), dados de demonstração, formatação pt-BR,
│                        volatilidade, espelho do motor financeiro e do grafo, stream SSE (snapshot + cursor + reconexão)
├── e2e/                 Playwright (1440 / 1024 / 390 px): modo demo e modo real simulado com `page.route`
├── backend/             FastAPI · SQLAlchemy · Alembic · sse-starlette · fastapi-mcp · 12 adaptadores
├── docs/                api-contract.md (fonte da verdade), openapi.json, adapters.md, backend.md, deploy.md, ci.md,
│                        mcp.md, manifest-skills.tsv, pesquisa-cruzamento-arbitragem.md
├── .mcp.json            MCPs do projeto (ver docs/mcp.md)
└── docker-compose.yml   postgres (pgvector) + api + worker (+ web, perfil opcional)
```

## Instalação e execução (frontend)

```bash
cd fronteira-fx
pnpm install --frozen-lockfile
cp .env.example .env.local          # só placeholders; .env.local nunca é versionado
pnpm dev                            # http://localhost:3000 — modo demonstração se nenhuma API estiver configurada
pnpm typecheck && pnpm lint && pnpm test && pnpm build
PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers pnpm test:e2e   # Playwright em 3 larguras, screenshots em dev/screenshots/
```

Variáveis do frontend, todas lidas **só no servidor** do Next pelo proxy `src/app/api/fx/[...path]/route.ts`:

| Variável | Uso |
|---|---|
| `FX_API_URL` | URL da API FastAPI (ex.: `http://localhost:8000`). O proxy repassa `GET/POST/PATCH/DELETE`, query string, `data_mode` e o stream SSE (`text/event-stream`). |
| `FX_API_KEY` | mesmo valor de `API_KEY` do backend; o proxy injeta `X-API-Key`. Nunca com prefixo `NEXT_PUBLIC_`, nunca versionada. |
| `NEXT_PUBLIC_API_URL` | só para dev local **sem chave**: o navegador fala direto com a API (exige `CORS_ORIGINS` no backend). Em produção fica vazia. |

O cliente (`src/lib/api/client.ts`) usa a base `/api/fx` por padrão. Sem `FX_API_URL` e sem `NEXT_PUBLIC_API_URL`, o app
entra em modo demonstração.

## Modos de dados

| Modo | Quando | Identificação |
|---|---|---|
| Demonstração | sem API configurada ou escolhido em Configurações | faixa permanente "Demonstração — dados ilustrativos"; todo registro tem `data_mode: "demo"` |
| Real | proxy apontando para o backend | snapshot inicial + SSE com replay por cursor + fallback de snapshot quando o stream cai |
| Simulação | simulador (`compare_routes`, `simulate_cycle`) sobre cotações reais | resultados do motor determinístico gravados com `data_mode: "simulation"`; a faixa de modo mostra "Simulação"; nunca entram no ranking real |

Os três modos nunca se misturam: o backend filtra por `data_mode` em todas as listagens.

## Backend, adaptadores e MCP

```bash
cd backend && uv sync --all-extras --dev
uv run pytest -q && uv run ruff check src tests
uv run uvicorn fronteira_fx.main:app --reload      # API em http://localhost:8000 (+ /mcp e /docs)
uv run python -m fronteira_fx.services.worker      # coletor: piso de 60 s por fonte, mesmo com force
```

Adaptadores (`backend/src/fronteira_fx/adapters/`, detalhes em `docs/adapters.md`): casas de câmbio por HTML —
`alberdi`, `bonanza`, `chaco`, `norte`, `maxicambios` (novo, ASU) e `myd` (novo, ASU e CDE); digitais — `nomad`,
`revolut`, `ueno`; por navegador (Playwright) — `westernunion`; referência — `bcp` (Banco Central do Paraguai) e
`dolarpy` (novo): agregador de terceiros (`dolar.melizeche.com`), **só referência**, `modality="reference"` e
`channel="aggregator"`, nunca vira preço executável nem de balcão e fica fora do ranking e do grafo.

MCP próprio em `/mcp` (18 ferramentas, 7 de escrita) e os demais servidores do `.mcp.json`: ver `docs/mcp.md`. Com
`API_KEY` definido, `X-API-Key` é obrigatório em todo `/mcp` e nas escritas; exporte `FX_API_KEY` com o mesmo valor
antes de abrir o Claude Code dentro de `fronteira-fx/`.

## Regras financeiras (implementadas no backend em `Decimal`, espelhadas no frontend só para a demo)

```
taxa efetiva   = crédito líquido / débito total
lucro de ciclo = valor final disponível − capital total alocado
ROI            = lucro líquido / capital total alocado
```

- Digital com ganho líquido positivo (mesmo microganho) entra no ranking principal; a formatação nunca arredonda para zero.
- Presencial entra no principal apenas se `ROI físico ≥ melhor ROI digital comparável + 0,01`.
- Custos essenciais desconhecidos → "estimativa incompleta", nunca lucro confirmado.
- Pesquisa adaptativa de R$ 5 mil a R$ 50 mil, começando por 5 / 10 / 25 / 50 mil.
- Dinheiro trafega como string decimal na API (inclusive `Cycle`/`Edge`); só a exibição arredonda (pt-BR, tabular).

## Docker Compose

```bash
cd fronteira-fx
cp .env.example .env                        # POSTGRES_PASSWORD e API_KEY são obrigatórios; sem defaults fracos
docker compose up -d --build                # postgres (pgvector) + api :8000 + worker (Playwright)
docker compose --profile web up -d --build  # idem + web: Next.js standalone com FX_API_URL=http://api:8000 e FX_API_KEY do .env
docker compose logs -f api worker
```

Healthcheck, ordem de subida, backup/restore e hosts: `docs/deploy.md` e `docs/backend.md`.

## Deploy na Vercel

```bash
pnpm exec vercel login
pnpm exec vercel deploy --yes          # prévia
pnpm exec vercel inspect <URL> --wait
pnpm exec vercel deploy --prod --yes   # produção, após validar
```

Defina `FX_API_URL` e `FX_API_KEY` como variáveis **de servidor** (sem `NEXT_PUBLIC_`), separadamente em Preview e
Production. Como todo o tráfego passa pelo proxy, as URLs de preview não precisam entrar em `CORS_ORIGINS`. Backend e
worker não rodam em Vercel Functions (duração limitada): veja `docs/deploy.md` para os containers.

## Licenças e atribuições

Lightweight Charts™ (TradingView, Apache-2.0) mantém o logotipo de atribuição no gráfico. Skills e repositórios de
referência instalados estão listados em `docs/manifest-skills.tsv` com commit e licença; MCPs em `docs/mcp.md`.
