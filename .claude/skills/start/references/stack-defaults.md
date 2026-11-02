# Stack defaults por tipo de projeto

## Web App / SaaS

| Camada       | Escolha padrão               | Alternativa             |
|--------------|------------------------------|-------------------------|
| Frontend     | Next.js 15 + React 19        | Vite + React            |
| Estilização  | Tailwind CSS 4               | CSS Modules             |
| Estado       | TanStack Query + Zustand     | SWR + Jotai             |
| Backend      | FastAPI (Python) ou Next API | Express / Hono          |
| ORM          | SQLAlchemy 2 + Alembic       | Drizzle ORM             |
| Banco        | PostgreSQL + pgvector         | SQLite (dev/simples)    |
| Autenticação | Clerk ou NextAuth.js         | Supabase Auth           |
| Testes       | Vitest + Playwright          | Jest + Cypress          |
| Lint         | ESLint + Prettier            | Biome                   |
| Pacotes JS   | pnpm                         | npm                     |
| Pacotes Py   | uv                           | poetry                  |
| CI           | GitHub Actions               | –                       |

## API / Microserviço

| Camada   | Escolha padrão       | Alternativa    |
|----------|----------------------|----------------|
| Runtime  | Python 3.13 + uv     | Node + Hono    |
| Framework| FastAPI              | Express        |
| DB       | PostgreSQL           | Redis + Postgres|
| Docs API | OpenAPI (automático) | –              |
| Docker   | Sim (sempre)         | –              |

## CLI / Tooling

| Camada    | Escolha padrão     |
|-----------|--------------------|
| Runtime   | TypeScript + tsx   |
| Empacotamento | tsup            |
| CLI parser| commander ou yargs |
| Testes    | Vitest             |

## Data / ML

| Camada     | Escolha padrão         |
|------------|------------------------|
| Runtime    | Python 3.13 + uv       |
| Data       | pandas + polars         |
| ML         | scikit-learn / PyTorch  |
| Embeddings | sentence-transformers   |
| Vector DB  | pgvector ou chromadb    |
| API        | FastAPI                 |

## Preferências do usuário (sempre aplicar)

- pnpm sobre npm/yarn
- TypeScript estrito
- ESLint + prettier
- Husky com TruffleHog no pre-commit e pre-push
- `./dev/` sempre gitignored
- Docker apenas se múltiplos serviços
- Testes antes de push
