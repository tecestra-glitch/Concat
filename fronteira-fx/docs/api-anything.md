# API Anything — prova de conceito

Checkout fixado: `goodnight000/api-anything` @ `9f3d15336aa520a389ad3674491b49009925696a` (MIT), em
`dev/external/api-anything` (fora do Git do produto). Instalação: `npm ci --ignore-scripts` + `npx tsc -p tsconfig.build.json`.
Configuração isolada deste projeto: `API_ANYTHING_HOME=fronteira-fx/.local/api-anything`, `setup --no-share --share-only`
→ `{"ok":true,"share":false}`. O setup geral (que altera outros clientes MCP) não foi executado. A skill foi copiada para
`.claude/skills/api-anything`.

## Resultado em 2026-11-02

| Comando | Resultado | Conclusão |
|---|---|---|
| `search "cambioschaco.com.py cotizaciones"` | catálogo compartilhado sem nenhum site paraguaio (135 sites, só correspondência lexical em ".com") | não há operação pronta para reutilizar; cada fonte precisa ser aprendida ou implementada |
| `capture https://www.cambioschaco.com.py/` | 39 requisições; único candidato útil é o **documento HTML** (55 kB, renderizado no servidor); o XHR restante é o desafio Cloudflare (`cdn-cgi/challenge-platform`) | a tabela de Chaco vem no HTML: coletor HTTP + parser (adaptador `chaco.py`) é o caminho correto; não existe JSON público a reproduzir |
| `learn https://www.bcp.gov.py/...` | exige `--args k=v` (parâmetros da consulta) | BCP é tabela estática diária; não há parâmetros a aprender, o adaptador `bcp.py` lê a página diretamente |

Uso previsto: `learn` em simuladores com parâmetros reproduzíveis (ex.: calculadora pública da Nomad, formulários com
query string). Western Union e Bonanza dependem de navegador/JavaScript e ficam com Playwright. Operações de escrita
permanecem desativadas porque os `args` do servidor em `.mcp.json` não incluem `--allow-writes` (a variável
`API_ANYTHING_READ_ONLY`, antes listada ali, não é lida pelo commit fixado e foi removida); a skill em
`.claude/skills/api-anything` traz o override do projeto: somente leitura, compartilhamento desativado, sem `publish`.
