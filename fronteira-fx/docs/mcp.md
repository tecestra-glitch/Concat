# MCPs do projeto

Configuração com escopo de projeto em `fronteira-fx/.mcp.json`.

| Servidor | Versão fixada | Finalidade | Dependência |
|---|---|---|---|
| context7 | `@upstash/context7-mcp@4.4.4` | documentação atual de bibliotecas | — |
| playwright | `@playwright/mcp@0.0.84` | inspeção e testes de interface | navegador Chromium local |
| firecrawl | `firecrawl-mcp@3.36.0` | pesquisa na web | `FIRECRAWL_API_KEY` no ambiente (sem chave o servidor não inicia; nada mais depende dele) |
| api-anything | checkout `dev/external/api-anything` @ `9f3d15336aa520a389ad3674491b49009925696a` | descoberta de consultas reproduzíveis em sites | `npm ci` + build no checkout; `API_ANYTHING_HOME=.local/api-anything`; compartilhamento desativado (`setup --no-share --share-only`); apenas leitura |
| frankfurter | oficial, remoto (`https://mcp.frankfurter.dev/`) | taxas de referência diárias, inclusive a cotação referencial do Banco Central do Paraguai (`/v2/providers/bcp/rates`) — só referência, nunca executável | — (sem chave) |
| fronteira-fx | próprio (`/mcp` da API FastAPI via fastapi-mcp) | `list_sources`, `get_quotes`, `request_quote`, `get_history`, `compare_routes`, `simulate_cycle`, `search_evidence` | API em execução (`FX_API_URL`, padrão `http://localhost:8000`) |

As versões acima foram confirmadas como publicadas no npm em 2026-11-02 (`npm view <pacote> version`).

Verificação de conexão: `claude mcp list` dentro de `fronteira-fx/` ou, no Claude Code, `/mcp`.
