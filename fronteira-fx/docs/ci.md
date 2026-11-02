# CI do Fronteira FX

Este documento explica as verificações automáticas (CI) do projeto: o que cada parte faz, como ler uma falha, como rodar as mesmas checagens no seu computador e como ligar o deploy na Vercel quando for o momento.

Dois workflows ficam em `.github/workflows/`, na **raiz** do repositório (o GitHub só lê workflows desse caminho, mesmo com o projeto numa subpasta):

- `fronteira-fx.yml`: tudo do projeto (frontend, backend, migrações, OpenAPI, hooks, imagens Docker).
- `secret-scan.yml`: varredura de segredos com TruffleHog em **todo** push e pull request do repositório, sem filtro de caminho. Antes ela era um job dentro do workflow do FX e um push só do app Rust não era varrido.

Os workflows do app Rust (`ci.yml`, `mobile.yml`) ignoram `fronteira-fx/**` e os dois arquivos acima (`paths-ignore`), então uma mudança só no FX não dispara os jobs do Rust.

## Quando roda

- `fronteira-fx.yml`: em todo `push` e todo `pull_request` que altere arquivos dentro de `fronteira-fx/` ou o próprio arquivo do workflow.
- `secret-scan.yml`: em todo `push` (qualquer branch) e todo `pull_request`, sem filtro de caminho. Um PR aberto a partir de uma branch do mesmo repositório é varrido duas vezes (push e PR); isso é aceito em troca da cobertura.
- Em um pull request, um novo push cancela a execução anterior. Em push para uma branch, a execução não é cancelada: o resultado precisa ficar registrado.
- Os workflows só leem o código. Não publicam nada, não fazem deploy e não usam segredos.

## Os jobs

| Workflow / job | Nome no GitHub | O que verifica | Falha impede o merge? |
|---|---|---|---|
| `secret-scan.yml` / `trufflehog` | Secret scan (TruffleHog) | Credenciais reais (verificadas) nos commits enviados | Sim, se marcado como obrigatório |
| `frontend` | Frontend (Next.js, demo mode) | Instalação, tipos, lint, testes unitários, build e testes de navegador em modo demonstração | Sim, se marcado como obrigatório |
| `e2e-real-mode` | End-to-end tests (real mode, mocked API) | `e2e/real-mode.spec.ts`: o terminal em modo real contra uma API simulada pelo próprio teste (`page.route`), sem backend | Sim, se marcado como obrigatório |
| `backend` | Backend (Python 3.13) | Lint (ruff) e testes (pytest) | Sim, se marcado como obrigatório |
| `alembic-check` | Migrations (Alembic on SQLite) | `alembic upgrade head` + `alembic check`: toda mudança em `models.py` precisa de migração | Sim, se marcado como obrigatório |
| `openapi-parity` | OpenAPI parity (docs/openapi.json) | `docs/openapi.json` é exatamente o que `scripts/export_openapi.py` gera | Sim, se marcado como obrigatório |
| `hooks` | Git hooks (husky) | Sintaxe, bit de execução e testes dos hooks em `fronteira-fx/.husky/` | Sim, se marcado como obrigatório |
| `docker` | Docker images (build only) | Constrói as duas imagens do backend, sem publicar | Não (`continue-on-error`) |

O workflow não bloqueia nada sozinho. Para que uma falha impeça o merge, marque o job como checagem obrigatória na proteção da branch (Settings, Branches, no GitHub). Atenção: com o `paths-ignore` dos workflows do Rust, um PR que toque só `fronteira-fx/` não gera os checks do Rust; se algum deles for obrigatório, o PR fica em "Expected — Waiting for status". Use os jobs do FX como obrigatórios ou um job-gate.

### `secret-scan.yml` (TruffleHog)

Roda o TruffleHog sobre os commits do push (de `github.event.before` a `github.event.after`) ou do pull request (da base ao head). Com `--only-verified`, só aparecem segredos que o TruffleHog confirmou estarem ativos, o que reduz falsos positivos.

A action está fixada por commit e o input `version` fixa o binário (`3.99.7`). O mesmo número está em `TRUFFLEHOG_VERSION` de `fronteira-fx/.husky/scan-secrets.sh`; o job `hooks` falha se os dois divergirem. Esse bump é manual: o Dependabot só move o commit da action.

Se algo aparecer, trate a credencial como vazada: revogue ou troque no provedor primeiro. Apagar o arquivo num commit novo não basta, porque o segredo continua no histórico.

### `frontend` (Node 22, pnpm 10)

Passos, na ordem:

1. `pnpm install --frozen-lockfile`: instala exatamente o que está em `pnpm-lock.yaml`. Falha se `package.json` e o lock não baterem.
2. `pnpm typecheck`: checa os tipos TypeScript.
3. `pnpm lint`: ESLint em `src` e `e2e`.
4. `pnpm test`: testes unitários com Vitest, em `src/**/*.test.ts(x)`.
5. `pnpm build`: build de produção do Next.js. O cache `.next/cache` é restaurado por uma chave com sistema, versão do Next e hash do `pnpm-lock.yaml`, sem chave de fallback: o conteúdo congela no primeiro build de cada lockfile + versão do Next.
6. Instala o Chromium do Playwright.
7. `pnpm test:e2e --grep-invert real-mode`: testes de navegador nos três perfis de tela (desktop 1440, tablet 1024 e celular 390), menos a spec do modo real, que tem job próprio. O próprio Playwright sobe o servidor (`next start`) usando o build do passo anterior.

Na CI o frontend roda em **modo demonstração**, porque nem `FX_API_URL` (proxy server-side) nem `NEXT_PUBLIC_API_URL` estão definidas. Por isso os testes de navegador não precisam do backend nem de banco.

### `e2e-real-mode`

Mesma instalação e build, depois `pnpm test:e2e e2e/real-mode.spec.ts`: a spec intercepta `**/api/fx/**` com `page.route` e simula a API (snapshot, stream, `410 Gone`), então o proxy real nunca é alcançado e não há backend. Os passos só rodam se a spec existir (`hashFiles`); o nome do arquivo precisa continuar contendo `real-mode`, porque o job `frontend` a exclui por esse texto. Relatório no artefato `playwright-report-real-mode`.

### `backend` (Python 3.13, uv)

1. `uv sync --locked --all-extras --dev`: instala as dependências a partir de `uv.lock`. O `--locked` faz o job falhar se `pyproject.toml` e `uv.lock` estiverem fora de sincronia, em vez de atualizar o lock sem ninguém perceber.
2. `uv run ruff check src tests`: lint e ordem dos imports.
3. `uv run pytest -q --junitxml=junit.xml`: testes. Usam SQLite, então a CI não sobe banco. O relatório JUnit é guardado como artefato.

### `alembic-check`

Com `DATABASE_URL` apontando para um SQLite vazio no diretório temporário do runner, roda `uv run alembic upgrade head` (aplica todas as migrações) e `uv run alembic check` (compara o resultado com os modelos do ORM). Falha quando `models.py` mudou sem migração correspondente. Os stores SQL dos módulos não montados (`watch/`, `notify/`, `rag/`, `memory/`) ficam fora do Alembic de propósito (ver `docs/backend.md`).

### `openapi-parity`

Roda `uv run python scripts/export_openapi.py` e falha se `git diff --exit-code -- docs/openapi.json` apontar diferença. Toda mudança de rota ou de schema no backend precisa vir com o arquivo regenerado no mesmo commit.

### `hooks`

`sh -n` nos três scripts de `fronteira-fx/.husky/`, bit de execução em `pre-commit` e `pre-push`, e `python3 -I fronteira-fx/.husky/tests/test_hooks.py` (repositório temporário e ferramentas falsas; também confere a versão do TruffleHog contra `secret-scan.yml`). Localmente: `pnpm test:hooks`.

### `docker` (não bloqueia)

Constrói duas imagens com BuildKit (os Dockerfiles usam `RUN --mount=type=cache`), sem enviar para registro nenhum:

- `backend/Dockerfile`: a API.
- `backend/Dockerfile.worker`: o coletor, com Playwright e Chromium.

O job tem `continue-on-error: true` porque as imagens ainda não foram construídas num ambiente com daemon Docker. Ele aparece com X vermelho, mas a execução continua verde. Quando os dois builds estiverem estáveis, remova essa linha, em um pull request próprio. Uma verificação barata que pode entrar antes disso: `docker compose -f fronteira-fx/docker-compose.yml --env-file fronteira-fx/.env.example config -q`.

## Como ler uma falha

1. Abra a aba **Actions** do repositório e clique na execução que falhou.
2. Clique no job com X vermelho. Dentro dele, o primeiro passo com X é onde o problema começou. Os passos depois dele aparecem como "skipped" e normalmente não precisam de atenção.
3. Compare com a tabela abaixo.

| O que aparece | Causa provável | O que fazer |
|---|---|---|
| `pnpm install` falha com "frozen-lockfile" | `package.json` mudou sem atualizar `pnpm-lock.yaml` | Em `fronteira-fx/`, rode `pnpm install` e commite o lock. |
| `uv sync` diz que o `uv.lock` precisa ser atualizado | Dependência mudou no `pyproject.toml` sem atualizar o lock | Em `fronteira-fx/backend/`, rode `uv lock` e commite o resultado. |
| `typecheck`, `lint` ou `ruff` apontam arquivo e linha | Erro de código | Corrija no ponto indicado e rode o mesmo comando local. |
| Um teste aparece como FAIL (Vitest ou pytest) | Regressão, ou teste instável | Rode só esse teste localmente. Se passa às vezes, é instabilidade: investigue antes de reexecutar. |
| `pnpm build` falha | Erro de compilação ou de tipos em uma página | Rode `pnpm build` localmente e leia a primeira mensagem de erro. |
| `test:e2e` falha | Layout ou comportamento diferente do esperado, em algum perfil de tela | Baixe o artefato `playwright-report` (ou `playwright-report-real-mode`). |
| Instalação do Chromium falha | Queda de rede momentânea | Reexecute o job. |
| `alembic check` reclama de diferença | `models.py` mudou sem migração | Em `fronteira-fx/backend/`, `uv run alembic revision --autogenerate -m "..."`, revise o arquivo gerado e commite. |
| `openapi-parity` acusa `docs/openapi.json` desatualizado | Rota ou schema mudou sem regenerar o arquivo | Em `fronteira-fx/backend/`, `uv run python scripts/export_openapi.py` e commite o resultado. |
| Job `hooks` falha | Hook sem `chmod +x`, erro de sintaxe, teste dos hooks quebrado ou versão do TruffleHog divergente | Rode `pnpm test:hooks` em `fronteira-fx/` e alinhe `TRUFFLEHOG_VERSION` com `secret-scan.yml`. |
| Job `docker` com X | Um dos Dockerfiles quebrou | Veja o passo de build no log. Não bloqueia a execução. |
| Job `Secret scan (TruffleHog)` falha | O TruffleHog achou uma credencial verificada | Trate como vazada (ver a seção do `secret-scan.yml`). |

Regra prática: uma falha que se repete quase sempre é erro real. Uma que muda de uma execução para outra é instabilidade, e vale a pena registrar qual teste é.

### Artefatos

No fim da página da execução, em "Artifacts", ficam os arquivos para baixar. Todos ficam disponíveis por 7 dias.

- `playwright-report` e `playwright-report-real-mode`: relatórios HTML dos testes de navegador. Baixe, descompacte e abra o `index.html`, ou rode `pnpm exec playwright show-report caminho/da/pasta` no seu computador. Testes que falharam trazem um *trace*: uma linha do tempo com ações, requisições e capturas, que mostra o que aconteceu no momento da falha.
- `playwright-screenshots`: as capturas de tela que os testes salvam por perfil de tela.
- `backend-junit`: resultado do pytest em XML. Útil para ver de uma vez todos os testes que falharam.

## Como rodar as mesmas verificações localmente

Pré-requisitos: Node 22.13 ou mais recente; pnpm (o projeto fixa a versão 10.28.0 no campo `packageManager`; com `corepack enable` o pnpm certo é usado automaticamente); uv, que instala o Python 3.13 se faltar; Docker, se quiser testar as imagens.

Frontend, dentro de `fronteira-fx/`:

```bash
pnpm install --frozen-lockfile
pnpm typecheck
pnpm lint
pnpm test
pnpm build
pnpm exec playwright install --with-deps chromium   # só na primeira vez
pnpm test:e2e                                        # inclui a spec do modo real
pnpm test:hooks                                      # testes dos hooks do husky
```

`pnpm test:all` roda typecheck, lint, test, build e test:e2e em sequência. Ele não instala o Chromium nem usa `--frozen-lockfile`, então rode o `playwright install` antes. Localmente, o Playwright reaproveita um servidor que já esteja na porta 3100. Na CI isso não acontece, porque a CI sempre sobe o seu.

Backend, dentro de `fronteira-fx/backend/`:

```bash
uv sync --locked --all-extras --dev
uv run ruff check src tests
uv run pytest -q
DATABASE_URL=sqlite:////tmp/fx-alembic-check.db uv run alembic upgrade head && DATABASE_URL=sqlite:////tmp/fx-alembic-check.db uv run alembic check
uv run python scripts/export_openapi.py && git diff --exit-code -- ../docs/openapi.json
```

Docker, dentro de `fronteira-fx/backend/` (é o mesmo contexto que a CI usa):

```bash
docker build -f Dockerfile -t fronteira-fx-api:ci .
docker build -f Dockerfile.worker -t fronteira-fx-worker:ci .
```

Varredura de segredos, na raiz do repositório, para o que ainda não foi enviado:

```bash
trufflehog git file://$PWD --since-commit origin/main --only-verified
```

## Hooks locais: a primeira barreira

Os hooks ficam em `fronteira-fx/.husky/` e são instalados pelo `pnpm install` (script `prepare`). Testes em `fronteira-fx/.husky/tests/test_hooks.py` (`pnpm test:hooks`).

- `pre-commit`: TruffleHog sobre o que está em stage (`--since-commit HEAD`), com o binário local ou, sem ele, com a imagem Docker da mesma versão (`TRUFFLEHOG_VERSION` em `scan-secrets.sh`). Sem binário e sem daemon, avisa e segue; com `FX_REQUIRE_SECRET_SCAN=1`, bloqueia. Se o commit toca `fronteira-fx/`, roda `lint-staged` (ESLint nos `.ts`/`.tsx` em stage; `ruff check` via `uv run --project backend` nos `.py` em stage; configuração em `fronteira-fx/package.json`) e `vitest run --changed`. Commits só do app Rust passam sem pnpm.
- `pre-push`: TruffleHog só nos commits novos de cada ref (`--since-commit <sha remota>`; ref nova varre o histórico inteiro). Se algum commit enviado toca `fronteira-fx/`, roda o Vitest completo e/ou o pytest completo, conforme o que mudou (frontend/backend).
- `git commit --no-verify` e `git push --no-verify` pulam os hooks. O `secret-scan.yml` roda no servidor do GitHub, em cada push e pull request, sem depender da sua máquina: é a segunda barreira, não a única.

## Deploy na Vercel (ainda não configurado)

Hoje não há deploy automático. O `package.json` tem os scripts `deploy` e `deploy:prod`, que enviam o projeto pela CLI a partir da sua máquina. Há duas formas de automatizar, e a recomendação é começar pela primeira.

### Opção A: integração Git da Vercel (recomendada)

- No painel da Vercel, importe o repositório e, em **Root Directory**, escolha `fronteira-fx`. Esse passo é obrigatório: a raiz do repositório é o app Rust, e a Vercel não acha o projeto Next.js sem ele.
- A Vercel faz o build sozinha: cada push gera uma URL de preview, e a `main` vai para produção.
- Não precisa de segredos no GitHub. Para exigir que o build da Vercel passe antes do merge, marque essa checagem como obrigatória na proteção da branch.
- Limitação: o build da Vercel não espera os jobs deste workflow. Se o deploy precisar esperar o CI ficar verde, use a opção B.

### Opção B: Vercel CLI dentro do GitHub Actions

- Adicione um job `deploy` ao workflow, com `needs: [frontend, backend]` e um `if` que limite a execução a push na `main`.
- Crie três secrets em Settings, Secrets and variables, Actions:
  - `VERCEL_TOKEN`: token de acesso criado no painel da Vercel.
  - `VERCEL_ORG_ID` e `VERCEL_PROJECT_ID`: os IDs gravados em `fronteira-fx/.vercel/project.json` pelo comando `vercel link`. Esse arquivo não vai para o Git (está no `.gitignore`).
- O job reproduz o fluxo do CLI: `vercel pull` para buscar a configuração de produção, `vercel build --prod` para compilar no runner e `vercel deploy --prebuilt --prod` para enviar o resultado pronto. Todos os comandos recebem o token pelo secret.

## Ajustes possíveis

- Todas as actions de `fronteira-fx.yml` e `secret-scan.yml` estão fixadas por commit (SHA de 40 caracteres) com a versão em comentário; o Dependabot (`.github/dependabot.yml`) move esses SHAs. O input `version` do TruffleHog em `secret-scan.yml` e `TRUFFLEHOG_VERSION` nos hooks são bumps manuais, sempre juntos.
- O `.github/dependabot.yml` cobre só `github-actions` (/) e `cargo` (/src); ecossistemas `npm` em `/fronteira-fx`, `uv` em `/fronteira-fx/backend` e `docker` em `/fronteira-fx/backend` ainda não entram.
- A chave do cache do Next não tem `restore-keys`: o conteúdo congela no primeiro build de cada lockfile + versão do Next. Para cache incremental por fonte, acrescente um hash de `src/**` à chave e use a chave atual como `restore-keys`.
- O `continue-on-error` do job `docker` deve sair assim que as imagens forem construídas com sucesso num ambiente com daemon.
