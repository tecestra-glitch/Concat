# CI do Fronteira FX

Este documento explica as verificações automáticas (CI) do projeto: o que cada parte faz, como ler uma falha, como rodar as mesmas checagens no seu computador e como ligar o deploy na Vercel quando for o momento.

O workflow fica em `.github/workflows/fronteira-fx.yml`, na **raiz** do repositório. Ele precisa estar ali porque o GitHub só lê workflows desse caminho, mesmo com o projeto numa subpasta.

## Quando roda

- Em todo `push` e todo `pull_request` que altere arquivos dentro de `fronteira-fx/` ou o próprio arquivo do workflow. Mudanças só no app Rust da raiz não disparam este workflow.
- Em um pull request, um novo push cancela a execução anterior, porque o código antigo já foi substituído. Em push para uma branch, a execução não é cancelada: o resultado na `main` precisa ficar registrado.
- O workflow só lê o código. Não publica nada, não faz deploy e não usa segredos.

## Os quatro jobs

| Job | O que verifica | Falha impede o merge? |
|---|---|---|
| `secrets` | Procura credenciais reais (verificadas) nos commits enviados | Sim, se marcado como obrigatório |
| `frontend` | Instalação, tipos, lint, testes unitários, build e testes de navegador | Sim, se marcado como obrigatório |
| `backend` | Lint (ruff) e testes (pytest) em Python 3.13 | Sim, se marcado como obrigatório |
| `docker` | Constrói as duas imagens do backend, sem publicar | Não |

O workflow não bloqueia nada sozinho. Para que uma falha impeça o merge, marque o job como checagem obrigatória na proteção da branch (Settings, Branches, no GitHub).

### `secrets`

Roda o TruffleHog sobre os commits do push ou do pull request. Com `--only-verified`, só aparecem segredos que o TruffleHog confirmou estarem ativos, o que reduz falsos positivos.

Se algo aparecer, trate a credencial como vazada: revogue ou troque no provedor primeiro. Apagar o arquivo num commit novo não basta, porque o segredo continua no histórico.

### `frontend` (Node 22, pnpm 10)

Passos, na ordem:

1. `pnpm install --frozen-lockfile`: instala exatamente o que está em `pnpm-lock.yaml`. Falha se `package.json` e o lock não baterem.
2. `pnpm typecheck`: checa os tipos TypeScript.
3. `pnpm lint`: ESLint em `src` e `e2e`.
4. `pnpm test`: testes unitários com Vitest, em `src/**/*.test.ts(x)`.
5. `pnpm build`: build de produção do Next.js.
6. Instala o Chromium do Playwright.
7. `pnpm test:e2e`: testes de navegador nos três perfis de tela (desktop 1440, tablet 1024 e celular 390). O próprio Playwright sobe o servidor (`next start`) usando o build do passo anterior.

Na CI o frontend roda em **modo demonstração**, porque `NEXT_PUBLIC_API_URL` fica vazia. Por isso os testes de navegador não precisam do backend nem de banco.

### `backend` (Python 3.13, uv)

1. `uv sync --locked --all-extras --dev`: instala as dependências a partir de `uv.lock`. O `--locked` faz o job falhar se `pyproject.toml` e `uv.lock` estiverem fora de sincronia, em vez de atualizar o lock sem ninguém perceber.
2. `uv run ruff check src tests`: lint e ordem dos imports.
3. `uv run pytest -q`: testes. Usam SQLite, então a CI não sobe banco. Um relatório JUnit é guardado como artefato.

### `docker` (não bloqueia)

Constrói duas imagens, sem enviar para registro nenhum:

- `backend/Dockerfile`: a API.
- `backend/Dockerfile.worker`: o coletor, com Playwright e Chromium.

O job tem `continue-on-error: true` porque os Dockerfiles ainda estão em andamento. Ele aparece com X vermelho, mas a execução continua verde. Quando os dois builds estiverem estáveis, remova essa linha, em um pull request próprio.

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
| `test:e2e` falha | Layout ou comportamento diferente do esperado, em algum perfil de tela | Baixe o artefato `playwright-report` (ver abaixo). |
| Instalação do Chromium falha | Queda de rede momentânea | Reexecute o job. |
| Job `docker` com X | Um dos Dockerfiles quebrou | Veja o passo de build no log. Não bloqueia a execução. |
| Job `secrets` falha | O TruffleHog achou uma credencial verificada | Trate como vazada (ver a seção do job `secrets`). |

Regra prática: uma falha que se repete quase sempre é erro real. Uma que muda de uma execução para outra é instabilidade, e vale a pena registrar qual teste é.

### Artefatos

No fim da página da execução, em "Artifacts", ficam os arquivos para baixar. Todos ficam disponíveis por 7 dias.

- `playwright-report`: relatório HTML dos testes de navegador. Baixe, descompacte e abra o `index.html`, ou rode `pnpm exec playwright show-report caminho/da/pasta` no seu computador. Testes que falharam trazem um *trace*: uma linha do tempo com ações, requisições e capturas, que mostra o que aconteceu no momento da falha.
- `playwright-screenshots`: as capturas de tela que os testes salvam, uma da página inicial e uma do simulador por perfil de tela.
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
pnpm test:e2e
```

`pnpm test:all` roda typecheck, lint, test, build e test:e2e em sequência. Ele não instala o Chromium nem usa `--frozen-lockfile`, então rode o `playwright install` antes. Localmente, o Playwright reaproveita um servidor que já esteja na porta 3100. Na CI isso não acontece, porque a CI sempre sobe o seu.

Backend, dentro de `fronteira-fx/backend/`:

```bash
uv sync --locked --all-extras --dev
uv run ruff check src tests
uv run pytest -q
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

## Varredura de segredos: complemento ao hook local

- O hook `fronteira-fx/.husky/pre-commit` roda o TruffleHog na sua máquina antes de cada commit e bloqueia o commit se achar um segredo verificado. Mas ele só funciona se o hook estiver instalado (o `pnpm install` cuida disso) e se o TruffleHog estiver disponível, como binário ou via Docker. Sem isso, o hook avisa e pula a varredura. E `git commit --no-verify` pula o hook inteiro.
- O job `secrets` roda no servidor do GitHub, em cada push e pull request, sem depender da sua máquina. É a segunda barreira, não a única.
- Limitação: o workflow só roda quando há mudança em `fronteira-fx/**` ou no próprio arquivo. Um push que altere apenas o app Rust da raiz não passa por essa varredura. Cobrir esse caso exigiria outro workflow, sem filtro de caminho.

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

- O TruffleHog segue `@main`, como a política do projeto pede. Se quiser uma versão fixa, troque para uma tag (por exemplo `@v3`).
- As demais actions estão fixadas em tags principais (`@v7`, `@v10` e assim por diante). Uma tag principal pode receber versões novas sem aviso. Para reprodutibilidade total, fixe o commit, como o restante do repositório faz.
- O `continue-on-error` do job `docker` deve sair assim que os Dockerfiles estiverem estáveis.
