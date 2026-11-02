# Fronteira FX — instruções para o Claude Code

Terminal pessoal de câmbio BRL · USD · PYG (CDE, ASU, PJC) com remessas, cartões e oportunidades.
Este projeto vive em `fronteira-fx/` dentro do repositório Concat (app Rust na raiz: não tocar).

## Comandos

```bash
pnpm install --frozen-lockfile && pnpm dev           # frontend em http://localhost:3000 (demo se sem API)
pnpm typecheck && pnpm lint && pnpm test && pnpm build
PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers pnpm test:e2e   # 1440 / 1024 / 390 px
cd backend && uv sync --all-extras --dev && uv run pytest -q && uv run ruff check src tests
cd backend && uv run uvicorn fronteira_fx.main:app --reload    # API + /mcp
docker compose up                                      # postgres (pgvector) + api + worker
```

## Regras que não mudam

- Dinheiro trafega como **string decimal** na API; `Decimal` no Python; só arredondar na exibição (pt-BR, tabular).
- `docs/api-contract.md` é a fonte da verdade entre frontend e backend. Mudou o contrato → mudar os dois lados e os testes.
- Modos de dados não se misturam: `real`, `simulation`, `demo` (`data_mode` em todo registro; faixa "Demonstração — dados ilustrativos").
- Ranking: digital com ganho líquido > 0 entra (microganho inclusive); presencial só com ganho > 0 **e** ROI ≥ melhor digital comparável + 0,01. Custo essencial desconhecido → `confidence: incomplete`, nunca "lucro confirmado".
- Cotações e cálculos vêm dos adaptadores, do banco e do motor; o RAG só responde documentação/tarifas/horários/evidências.
- Contexto de cotação (origem, destino, moedas, montante, pagamento, recebimento, banco, canal, promoção) nunca se mistura.
- Sites sem API: sondagem adaptativa (mín. 60 s por fonte), requisições condicionais, hash do conteúdo, recuo após erro. Nunca martelar.
- Nada executa movimentação financeira. Conexão de contas e execução são fases posteriores e começam por aprovação manual.
- Segredos só no backend por variáveis de ambiente. Nunca em `NEXT_PUBLIC_*`, nunca no Git (husky + TruffleHog).
- Testes Playwright esperam elementos específicos; nunca `networkidle` (o app mantém um stream aberto).
- Lint do Next 16 segue as regras do React Compiler: sem `setState` dentro de `useEffect` (usar `useSyncExternalStore`, ver `src/lib/use-now.ts`).

## Mapa

| Caminho | O que é |
|---|---|
| `src/app`, `src/components`, `src/lib` | telas, componentes, cliente de API, demo, SSE, grafo (espelho TS) |
| `backend/src/fronteira_fx/{adapters,engine,graph,watch,notify,rag,memory,api,services}` | adaptadores por provedor, motor financeiro, grafo de posições, monitor, alertas, RAG, memória, rotas |
| `backend/evals` | goldens e rubricas (DeepEval opcional) |
| `docs/` | contrato, adaptadores, backend, deploy, MCPs, pesquisa, testes, screenshots |
| `.claude/skills` (raiz do repo) | skills instaladas por commit fixo; manifesto em `docs/manifest-skills.tsv` |
| `dev/` | pasta de desenvolvedor, fora do Git (checkouts externos, screenshots, relatórios) |
