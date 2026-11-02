# Catálogo de MCPs por categoria

Revisado em 2026-11-02 contra o npm/PyPI. Regras antes de instalar qualquer item:

- Sempre `claude mcp add --scope project` (grava em `.mcp.json`; sem o flag vai para o escopo local do usuário).
- Sempre versão fixada (`<pacote>@<versão>`); confira `npm view <pacote> version deprecated` antes.
- Pacotes *deprecated* ou em quarentena de segurança (`0.0.1-security`) ficam de fora. Os servidores de referência
  `git` e `fetch` são **Python** (`uvx`), não npm: os nomes npm homônimos foram removidos pelo npm.
- Nunca instale servidores que executam transações financeiras (pagamentos, ordens em exchanges).
- Segredos só como `${VARIAVEL}` no `.mcp.json`, nunca literais.

## Bancos de dados

| MCP                  | Pacote                                  | Quando usar                     |
|----------------------|-----------------------------------------|---------------------------------|
| `sqlite`             | `mcp-server-sqlite` (PyPI, `uvx`)       | SQLite local                    |
| `postgres`           | `@modelcontextprotocol/server-postgres` **descontinuado no npm**; prefira o MCP oficial do provedor (Neon, Supabase, etc.) | PostgreSQL como ferramenta |

## Código / Git

| MCP              | Pacote                                                   | Quando usar                    |
|------------------|----------------------------------------------------------|--------------------------------|
| `github`         | servidor oficial remoto do GitHub (`https://api.githubcopilot.com/mcp/`, `type: http`); o npm `@modelcontextprotocol/server-github` está **descontinuado** | PRs, issues, código |
| `filesystem`     | `@modelcontextprotocol/server-filesystem`                | Acesso a pastas locais         |
| `git`            | `mcp-server-git` (PyPI, `uvx mcp-server-git`) — o nome npm é um pacote de quarentena | Operações git avançadas |

## Pesquisa / Web

| MCP              | Pacote                                   | Quando usar                    |
|------------------|------------------------------------------|--------------------------------|
| `firecrawl`      | `firecrawl-mcp`                          | Scraping e pesquisa web        |
| `fetch`          | `mcp-server-fetch` (PyPI, `uvx`)         | HTTP requests                  |
| `context7`       | `@upstash/context7-mcp`                  | Docs de bibliotecas ao vivo    |

`@modelcontextprotocol/server-brave-search` e `server-puppeteer` estão descontinuados: use `firecrawl` e `playwright`.

## Produtividade

| MCP              | Pacote                                   | Quando usar                    |
|------------------|------------------------------------------|--------------------------------|
| `memory`         | `@modelcontextprotocol/server-memory`    | Memória persistente            |
| `playwright`     | `@playwright/mcp`                        | Browser automation e E2E       |
| `notion`         | `mcp-notion-server`                      | Docs/wiki                      |

`@modelcontextprotocol/server-slack` está descontinuado; o toolkit de agentes da Stripe executa pagamentos e não entra.

## Instalação rápida

```bash
# Adicionar MCP ao projeto (gera entrada em .mcp.json): sempre --scope project e versão fixada
claude mcp add --scope project <nome> -- npx -y <pacote>@<versão> [args]

# Exemplo: Filesystem (acesso a uma pasta)
claude mcp add --scope project files -- npx -y @modelcontextprotocol/server-filesystem@<versão> /caminho/projeto

# Exemplo: servidor Python de referência
claude mcp add --scope project git -- uvx mcp-server-git@<versão>

# Exemplo: servidor remoto http
claude mcp add --scope project --transport http github https://api.githubcopilot.com/mcp/
```
