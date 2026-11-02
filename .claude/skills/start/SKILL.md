---
name: start
description: >
  Inicializa qualquer projeto novo do zero: brainstorm estruturado → descoberta de
  repositórios, MCPs e skills relacionados → download/instalação automática →
  estrutura de pastas e git com hooks → orquestração de agentes paralelos com
  worktrees para máximo throughput. Dispare ao começar qualquer coisa nova, mesmo
  sem saber o tech stack ainda. Também detecta projetos existentes e retoma de onde
  parou, criando apenas o que estiver faltando.
---

# /start — Project Launchpad

Você vai iniciar (ou retomar) um projeto de forma sistemática, maximizando a
paralelização do trabalho. Siga as fases em ordem; cada uma desbloqueia a próxima.

---

## Fase 0 — Brainstorm estruturado (sempre primeiro)

Antes de criar um único arquivo:

1. **Leia o que já existe** no diretório atual:
   ```bash
   ls -la && cat CLAUDE.md 2>/dev/null || true && cat README.md 2>/dev/null || true
   ```
2. Invoque `superpowers:brainstorming` para estruturar o problema com o usuário.
   - Extraia: nome do projeto, objetivo central, stack desejada, integrações,
     fontes de dados, público-alvo, restrições (prazo, orçamento, compliance).
   - Pergunte se há repositórios de referência já conhecidos.
3. Registre o resultado em `./dev/brainstorm.md` (esta pasta é sempre gitignored).

---

## Fase 1 — Descoberta paralela (4 agentes simultâneos)

Lance **todos de uma vez** com o `Agent` tool. Cada um recebe contexto do brainstorm:

| Agente | Tarefa | Ferramentas |
|--------|--------|-------------|
| `discover-repos` | GitHub: buscar 5–10 repos open-source mais relevantes para o stack. Para cada um: URL, estrelas, licença, por que é relevante, o que reutilizar. | WebSearch, WebFetch |
| `discover-mcps` | MCP registry + awesome-mcp-servers: listar MCPs que o projeto vai precisar (bases de dados, APIs externas, ferramentas). Para cada um: nome, npm/pip, propósito. | WebSearch, WebFetch |
| `discover-skills` | Listar skills já instaladas que se aplicam. Também buscar skills de terceiros se houver lacuna clara. | Read (`.claude/skills/`), WebSearch |
| `discover-stack` | Dado o objetivo, propor: linguagem, framework, ORM/banco, testes, CI, Docker (só se necessário), lint, formatação — justificando cada escolha. Verificar compatibilidade com as preferências do usuário (pnpm, TypeScript, eslint, husky, TruffleHog). | Read, WebSearch |

Coleta os resultados em `./dev/discovery/`.

---

## Fase 2 — Plano de execução

Com os resultados da descoberta, monte:

1. **`./dev/plano.md`** — lista de tarefas com dependências, agrupadas por domínio
   (infra, backend, frontend, testes, docs, CI/CD). Use checkboxes `- [ ]`.
2. **Árvore de diretórios** — a estrutura de pastas final esperada.
3. **Lista de workers** — quantos agentes paralelos são seguros dado o projeto
   (regra: 1 por domínio independente, máx. 8 por turno sem aprovação explícita).
4. Apresente o plano ao usuário e aguarde confirmação antes de prosseguir.

---

## Fase 3 — Setup do repositório

Execute em sequência (ordem importa):

```bash
# 1. Git init se não existir
git init 2>/dev/null || true
git checkout -b main 2>/dev/null || git checkout main 2>/dev/null || true

# 2. Criar estrutura base de pastas (adapte ao stack)
mkdir -p src tests docs dev .github/workflows
echo "/dev/" >> .gitignore
echo "node_modules/" >> .gitignore
echo ".env" >> .gitignore
echo ".env.local" >> .gitignore

# 3. Criar arquivo de configuração do Claude
# (veja templates/CLAUDE.md.tpl nesta skill)
```

Gere os seguintes arquivos a partir dos templates desta skill:
- `CLAUDE.md` — regras do projeto, stack, comandos úteis, padrões.
- `.gitignore` — adequado ao stack detectado.
- `.claude/settings.json` — permissões para o projeto.
- `README.md` — esqueleto com: objetivo, instalação, comandos, contribuição.

---

## Fase 4 — Instalação de MCPs e skills

Para cada MCP descoberto na Fase 1:

```bash
# npm MCPs
claude mcp add <nome> -- npx -y <pacote> [args]

# Ou adicionar manualmente ao .mcp.json do projeto
```

Para cada skill relevante não instalada:
- Verifique se já existe em `.claude/skills/`.
- Se não, clone/copie conforme instruções do repositório da skill.

Atualizar o `.mcp.json` do projeto com todos os servidores configurados.

---

## Fase 5 — Hooks git com Husky + TruffleHog

```bash
# Instalar husky (se package.json existir)
pnpm add -D husky 2>/dev/null || pip install pre-commit 2>/dev/null || true

# Pre-commit: lint + testes rápidos
cat > .husky/pre-commit << 'EOF'
#!/bin/sh
set -e
# TruffleHog: bloqueia em segredos encontrados (exit 183)
if command -v trufflehog >/dev/null 2>&1; then
  trufflehog git file://. --since-commit HEAD --only-verified --fail
  TH=$?
  [ $TH -eq 183 ] && echo "❌ Segredo detectado pelo TruffleHog" && exit 1
fi
# Testes rápidos
pnpm test --run 2>/dev/null || pytest -q --timeout=30 2>/dev/null || true
EOF
chmod +x .husky/pre-commit

# Pre-push: TruffleHog completo
cat > .husky/pre-push << 'EOF'
#!/bin/sh
set -e
if command -v trufflehog >/dev/null 2>&1; then
  trufflehog git file://. --only-verified --fail
  TH=$?
  [ $TH -eq 183 ] && echo "❌ Segredo no histórico detectado" && exit 1
fi
EOF
chmod +x .husky/pre-push
```

---

## Fase 6 — Orquestração com git worktrees (máximo paralelismo)

Esta é a fase de execução real. Lance **todos os agentes de domínio de uma vez**,
cada um em seu próprio worktree para evitar conflitos de arquivo:

```javascript
// Script gerado em ./dev/workflow-start.js (use com Workflow tool)
export const meta = {
  name: 'project-start',
  description: 'Implementação paralela por domínio com worktrees',
  phases: [
    { title: 'Scaffold', detail: 'Estrutura base + configurações' },
    { title: 'Build',    detail: 'Implementação por domínio' },
    { title: 'QA',       detail: 'Testes + revisão de segurança' },
    { title: 'Merge',    detail: 'Integração dos domínios' },
  ],
}

// Domínios independentes — cada um em seu worktree
const DOMAINS = [
  { key: 'backend',  prompt: '...' },
  { key: 'frontend', prompt: '...' },
  { key: 'infra',    prompt: '...' },
  { key: 'tests',    prompt: '...' },
  { key: 'docs',     prompt: '...' },
]

phase('Scaffold')
await parallel(DOMAINS.map(d => () =>
  agent(d.prompt, { label: `build:${d.key}`, phase: 'Build', isolation: 'worktree' })
))
```

Regras de worktrees:
- Cada agente recebe um contexto mínimo: seu domínio, a árvore de arquivos atual,
  as interfaces/contratos que precisa respeitar.
- Agentes de domínio **não modificam** arquivos fora do seu escopo.
- Um agente "merge" final integra tudo, resolve conflitos e roda os testes.

Gere o workflow em `./dev/workflow-start.js` preenchido com os prompts reais
extraídos do plano da Fase 2.

---

## Fase 7 — Primeiro commit e CI

```bash
git add -A
git commit -m "feat: project scaffolding — <nome do projeto>

Stack: <lista>
MCPs: <lista>
Skills: <lista>

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"

# GitHub Actions CI básico
mkdir -p .github/workflows
# (usar template desta skill: templates/ci.yml.tpl)
```

---

## Ao final, reporte:

```
✅ /start concluído — <nome do projeto>

Estrutura:  <N> arquivos, <N> pastas
MCPs:       <lista instalada>
Skills:     <lista ativa>
Workers:    <N agentes rodaram em paralelo>
Worktrees:  <N domínios>
Próximo:    <próxima ação recomendada>
```

---

## Regras desta skill

- **Nunca sobrescreva** arquivos existentes sem ler primeiro e confirmar com o usuário.
- **`./dev/` sempre gitignored** — rasunhos, brainstorms, benchmarks ficam aqui.
- **Docker só se necessário** — não adicione por padrão, apenas se o projeto tiver
  múltiplos serviços ou o usuário pedir.
- **Secrets nunca em git** — use `.env.example` com placeholders; valores reais
  ficam em `.env` (gitignored) ou em variáveis de ambiente do CI.
- **pnpm sobre npm/yarn** para projetos JS/TS (preferência do usuário).
- **TypeScript sobre JavaScript** para projetos JS novos.
- **Ao usar o Workflow tool**, invoque `superpowers:workflow-authoring` primeiro
  para escrever o script corretamente.

## Referências

- `references/stack-defaults.md` — opções de stack por tipo de projeto
- `references/mcp-catalog.md` — MCPs mais usados por categoria
- `templates/CLAUDE.md.tpl` — template do CLAUDE.md do projeto
- `templates/ci.yml.tpl` — template de GitHub Actions CI
- `scripts/discover.sh` — busca MCPs/repos/skills via CLI
- `scripts/setup-git.sh` — setup completo do repositório git
