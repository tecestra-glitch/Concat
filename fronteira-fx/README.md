# Fronteira FX

Terminal pessoal de câmbio, remessas, cartões e oportunidades financeiras para **BRL · USD · PYG** em
Ciudad del Este, Asunción e Pedro Juan Caballero, cobrindo Western Union, ueno, Nomad, Revolut e casas de câmbio.

> Este projeto vive na pasta `fronteira-fx/` do repositório. O frontend Next.js fica aqui na raiz da pasta
> (para o deploy na Vercel use **Root Directory = `fronteira-fx`**); o backend Python fica em `backend/`.

## Estrutura

```
fronteira-fx/
├── src/                 Next.js 16 · React 19 · TypeScript · Tailwind 4 · shadcn-style UI
│   ├── app/             telas: /, /mercados, /oportunidades, /simulador, /contas, /fontes, /diario, /configuracoes
│   ├── components/      shell, mercados, gráficos (Lightweight Charts), oportunidades, simulador
│   └── lib/             contrato de API (types), cliente, dados de demonstração, formatação pt-BR,
│                        volatilidade, espelho do motor financeiro, stream SSE (snapshot + cursor + reconexão)
├── e2e/                 Playwright (1440 / 1024 / 390 px)
├── backend/             FastAPI · SQLAlchemy · Alembic · sse-starlette · fastapi-mcp · adaptadores
├── docs/                api-contract.md, adapters.md, backend.md, openapi.json, manifest-skills.tsv
└── docker-compose.yml   postgres (pgvector) + api + worker
```

## Instalação e execução (frontend)

```bash
cd fronteira-fx
pnpm install --frozen-lockfile
pnpm dev            # http://localhost:3000 — modo demonstração se NEXT_PUBLIC_API_URL estiver vazio
pnpm test           # unitários (Vitest)
pnpm build && pnpm test:e2e   # Playwright em 3 larguras, screenshots em dev/screenshots/
```

Variáveis: copie `.env.example` para `.env.local`. Só `NEXT_PUBLIC_API_URL` é lida pelo navegador; segredos ficam no backend.

## Modos de dados

| Modo | Quando | Identificação |
|---|---|---|
| Demonstração | sem API configurada ou escolhido em Configurações | faixa permanente "Demonstração — dados ilustrativos"; todo registro tem `data_mode: "demo"` |
| Real | `NEXT_PUBLIC_API_URL` aponta para o backend | snapshot inicial + SSE com replay por cursor + fallback de snapshot a cada 30 s |
| Simulação sobre dados reais | simulador com API real | resultados vêm do motor determinístico do backend |

Registros de demonstração nunca se misturam aos reais: o backend filtra por `data_mode` em todas as listagens.

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

## Deploy na Vercel

```bash
pnpm exec vercel login
pnpm exec vercel deploy --yes          # prévia
pnpm exec vercel inspect <URL> --wait
pnpm exec vercel deploy --prod --yes   # produção, após validar
```

Configure `NEXT_PUBLIC_API_URL` separadamente em Preview e Production. Backend e worker não rodam em Vercel Functions
(duração limitada): veja `docs/backend.md` para os containers.

## Licenças e atribuições

Lightweight Charts™ (TradingView, Apache-2.0) mantém o logotipo de atribuição no gráfico. Skills e repositórios de
referência instalados estão listados em `docs/manifest-skills.tsv` com commit e licença.
