# Catálogo de MCPs por categoria

## Bancos de dados

| MCP                  | Pacote npm/pip                    | Quando usar                     |
|----------------------|-----------------------------------|---------------------------------|
| `mcp-postgres`       | `@modelcontextprotocol/server-postgres` | PostgreSQL como ferramenta     |
| `mcp-sqlite`         | `mcp-server-sqlite`               | SQLite local                    |
| `mcp-redis`          | `mcp-server-redis`                | Cache, filas, pub/sub           |

## Código / Git

| MCP              | Pacote                            | Quando usar                    |
|------------------|-----------------------------------|--------------------------------|
| `github`         | `@modelcontextprotocol/server-github` | PRs, issues, código           |
| `filesystem`     | `@modelcontextprotocol/server-filesystem` | Acesso a pastas locais    |
| `git`            | `mcp-server-git`                  | Operações git avançadas        |

## Pesquisa / Web

| MCP              | Pacote                            | Quando usar                    |
|------------------|-----------------------------------|--------------------------------|
| `firecrawl`      | `firecrawl-mcp`                   | Scraping e pesquisa web        |
| `brave-search`   | `@modelcontextprotocol/server-brave-search` | Busca web             |
| `fetch`          | `@modelcontextprotocol/server-fetch` | HTTP requests               |

## Produtividade

| MCP              | Pacote                            | Quando usar                    |
|------------------|-----------------------------------|--------------------------------|
| `memory`         | `@modelcontextprotocol/server-memory` | Memória persistente          |
| `puppeteer`      | `@modelcontextprotocol/server-puppeteer` | Browser automation         |
| `playwright`     | `@playwright/mcp`                 | Testes E2E via MCP            |

## APIs de negócio

| MCP              | Pacote                            | Quando usar                    |
|------------------|-----------------------------------|--------------------------------|
| `stripe`         | `stripe-agent-toolkit`            | Pagamentos                     |
| `notion`         | `mcp-notion-server`               | Docs/wiki                      |
| `slack`          | `@modelcontextprotocol/server-slack` | Notificações               |

## IA / Embeddings

| MCP              | Pacote                            | Quando usar                    |
|------------------|-----------------------------------|--------------------------------|
| `context7`       | `@upstash/context7-mcp`           | Docs de bibliotecas ao vivo    |
| `anthropic`      | built-in via SDK                  | Chamar Claude dentro do agente |

## Instalação rápida

```bash
# Adicionar MCP ao projeto (gera entrada em .mcp.json)
claude mcp add <nome> -- npx -y <pacote> [args]

# Exemplo: PostgreSQL
claude mcp add postgres -- npx -y @modelcontextprotocol/server-postgres postgresql://localhost/mydb

# Exemplo: Filesystem (read-only)
claude mcp add files -- npx -y @modelcontextprotocol/server-filesystem /caminho/projeto
```
