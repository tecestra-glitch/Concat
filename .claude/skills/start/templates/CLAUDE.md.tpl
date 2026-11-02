# {{PROJECT_NAME}}

## Objetivo
{{PROJECT_DESCRIPTION}}

## Stack
- **Linguagem**: {{LANGUAGE}}
- **Framework**: {{FRAMEWORK}}
- **Banco**: {{DATABASE}}
- **Testes**: {{TESTS}}
- **CI**: GitHub Actions

## Comandos rápidos

```bash
# Instalação
{{INSTALL_CMD}}

# Dev
{{DEV_CMD}}

# Testes
{{TEST_CMD}}

# Build
{{BUILD_CMD}}

# Lint
{{LINT_CMD}}
```

## Estrutura de pastas

```
{{FOLDER_TREE}}
```

## Padrões de código

- TypeScript strict: sempre
- Commits: Conventional Commits (`feat:`, `fix:`, `docs:`, `chore:`)
- PRs: sempre com testes passando
- Secrets: nunca em git, use `.env` (gitignored)
- Logs: structured JSON em produção

## Branch de desenvolvimento

Trabalhe sempre em `claude/<descrição-kebab>`. Nunca commite direto em `main`.

## MCPs disponíveis

{{MCP_LIST}}

## Skills ativas

{{SKILLS_LIST}}

## Agentes e workers

- Máx. workers paralelos seguros: {{MAX_WORKERS}}
- Worktrees para edição paralela: sim
- Workflow scripts em: `./dev/`

## Notas do projeto

{{PROJECT_NOTES}}
