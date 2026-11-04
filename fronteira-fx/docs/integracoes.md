# Integrações: como achar a API de um site e transformar em fonte

Este guia mostra como adicionar uma casa de câmbio, banco ou fintech que não tem API oficial. A ideia: todo site
busca os próprios números no backend com uma chamada interna (um JSON). Achamos essa chamada, repetimos com HTTP
comum, sem navegador, e viramos um adaptador. Nada disso sai da máquina: não usamos serviço de terceiros.

## 1. Entender o selo de integração

Cada fonte declara como é alcançada (campo `integration`, visível em `GET /v1/sources`, em `list_sources` no MCP
e como selo na tela de Fontes):

| Valor | O que significa | Exemplo |
|---|---|---|
| `api_oficial` | API pública documentada, do provedor ou da fonte oficial | BCP (referência), dolarPy |
| `endpoint_interno` | JSON que o próprio site chama; repetimos com HTTP | Chaco, Bonanza, Alberdi, Revolut, Nomad |
| `html` | página renderizada pelo servidor, lida com seletores | MaxiCambios, M&D, Norte, ueno |
| `navegador` | só aparece depois de interação; precisa de navegador | Western Union |

Prefira sempre a opção mais simples que funciona: `api_oficial` > `endpoint_interno` > `html` > `navegador`.

## 2. Descobrir a chamada interna com `fx-discover`

Ferramenta de desenvolvimento. Ela abre a página **uma vez**, sem login e sem cookies, observa as chamadas por
20 segundos e ranqueia as que parecem cotação.

```bash
cd fronteira-fx/backend
export PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers
uv run fx-discover https://www.exemplo.com.py/ --seconds 20 --out ../dev/discover/exemplo.json
```

- Se o Chromium do Playwright instalado não estiver em `PLAYWRIGHT_BROWSERS_PATH`, aponte o executável com
  `FX_DISCOVER_CHROMIUM=/caminho/para/chrome-headless-shell`. Sem a variável, usa o padrão do Playwright.
- `--seconds` vai de 5 a 120 (padrão 20).
- `--out` grava o relatório JSON. Use uma pasta fora do Git (`dev/` ou `backend/.local/`).
- O relatório mostra, para cada candidato: método, URL, parâmetros, cabeçalhos necessários, tipo, tamanho e um
  trecho da resposta **já sem dados pessoais**.
- A coluna `sem nav.` diz se a mesma chamada funcionou com HTTP comum, uma única vez. Se disser `não`, leia a
  nota de cabeçalhos omitidos: normalmente é token ou cookie, e nesse caso o site depende de sessão do navegador.

A ferramenta recusa URLs que não sejam `http(s)` públicas (nada de `localhost`, IP privado ou `file:`) e recusa
visitar o mesmo site de novo antes de 60 segundos.

## 3. Gerar o esqueleto do adaptador

Com o candidato 1 escolhido, gere os arquivos com um id novo (minúsculas, sem traço):

```bash
uv run fx-discover https://www.exemplo.com.py/ --scaffold exemplo
```

Isso cria três arquivos, **sem registrar nada**:

- `backend/src/fronteira_fx/adapters/exemplo.py`: classe, `info` (com `integration` preenchido), `fetch` e um
  `parse` com `TODO` marcando o que falta.
- `backend/tests/adapters/fixtures/exemplo.json` (ou `.html`): a resposta capturada, já sanitizada.
- `backend/tests/adapters/test_exemplo.py`: teste offline do parse. **Ele falha de propósito** até o mapeamento
  estar pronto.

Não sobrescrevemos arquivos existentes. Se o id já existir, escolha outro.

## 4. Completar o adaptador

1. Leia a fixture e mapeie cada cotação para `QuoteDraft` (compra, venda, moeda, filial, cidade).
2. Troque os `TODO` de nome, tipo, cidades, moedas e limitações.
3. Tire de `URL` qualquer valor `<redigido>`: parâmetros secretos vêm de variável de ambiente, nunca do código.
4. Rode `uv run pytest tests/adapters/test_exemplo.py -q` até passar.
5. Revise a fixture antes do commit: confirme que não sobrou nada pessoal.
6. Só então registre o módulo em `adapters/registry.py` e rode a bateria completa.

Use `_common` e `_http` (`http_get`, `parse_decimal`, `build_evidence`, `finalize`) como os adaptadores existentes.

## 5. Como a fonte aparece no MCP e na API

Depois de registrar, nada mais é preciso:

- `GET /v1/sources` e a ferramenta MCP `list_sources` passam a listar a fonte, com `integration`.
- A tela Fontes mostra o selo ao lado do estado de saúde.
- O coletor sonda a fonte no intervalo `poll_interval_s` (mínimo de 60 s) e grava evidências com hash.

Se você mudou o contrato da API, regenere `docs/openapi.json`:
`cd backend && uv run python scripts/export_openapi.py`.

## 6. Regras que não mudam

- **Sondagem mínima de 60 s por fonte.** O `fx-discover` aplica isso por site; o coletor também.
- **Requisições condicionais.** Quando o site devolve `Last-Modified` ou `ETag`, o coletor reaproveita a
  validação e não baixa o que não mudou. Nunca martele: em erro, o recuo cresce.
- **Termos de uso.** Leia os termos e o `robots.txt` do site antes de adicionar. Se o site proíbe coleta,
  não adicione como coletor automático; se a informação for útil, registre-a manualmente, com a nota.
- **Nunca área logada de banco.** Não entramos com conta, não guardamos senha e não pedimos código de acesso.
  Contas são fase posterior, com aprovação manual.
- **Nunca enviar cookies ou dados a terceiros.** O relatório omite cabeçalhos de sessão (só o nome aparece) e
  redige e-mails, números longos e tokens. Os relatórios ficam fora do Git.
- **Segredos só no backend**, por variável de ambiente.
- **Modo de dados.** Fonte real grava `data_mode="real"`; nunca misture com `demo`.
- **Não há captcha nem login automático.** Se o site bloqueia ou pede sessão, o adaptador responde `BLOCKED` ou
  `NEEDS_SESSION` e a tela mostra o motivo.

## 7. Checklist

- [ ] `fx-discover` rodou uma vez e o candidato foi escolhido com motivo claro
- [ ] `integration` correto no adaptador (o menor que funciona)
- [ ] fixture revisada, sem dados pessoais
- [ ] teste de parse passa
- [ ] registrado em `registry.py` e aparece em `GET /v1/sources`
- [ ] selo visível na tela Fontes
- [ ] termos de uso lidos e anotados nas `limitations`

## 8. Caso Western Union: a cotação não saiu do navegador

Tentativa de achar um endpoint interno para a Western Union (`westernunion`, BR → PY) em `https://www.westernunion.com/br/pt/web/send-money/start`.
Resultado: **não há endpoint sem navegador para a cotação.** A fonte continua `integration: navegador` e fica fora do modo serverless.

O que a descoberta viu (duas visitas à página inicial, sem login, sem cookies, sem interação):

- A página é um SPA Angular. A cotação só aparece depois do fluxo interativo (país, montante, recebimento, pagamento). A chamada que a traz, `POST wuconnect/prices/catalog`, **não apareceu**, porque só dispara depois dessa interação.
- Dois candidatos GET responderam 200 sem navegador, mas nenhum traz cotação:
  - `content/v2/content/web/wucom` (JSON de conteúdo do site, cerca de 1 MB): textos de marketing. A pontuação subiu por palavras como "compra" e "venda" dentro do texto, então o replay "funciona" é **falso positivo** da ferramenta.
  - `wuconnect/rest/api/v1.0/price/corridors/BR/BRL`: lista de países e moedas, sem taxa.
- O cabeçalho `cookie` foi omitido, como de costume; a documentação do adaptador já indicava que o preço depende de fingerprint do navegador.

Decisão: não implementamos o caminho `endpoint_interno` para a Western Union. Não tentamos reproduzir o `prices/catalog` sem navegador, nem contornar fingerprint, cookie ou proteção anti-robô: isso ficaria fora da regra "não contornar bloqueio".
Para a cotação, a fonte segue só pelo navegador (Playwright, extra `browser`), fora do modo serverless. Se a Western Union publicar uma API ou se um futuro teste autorizado mostrar a chamada `prices/catalog` com um replay limpo, reabrimos esta seção.

Ajuste de ferramenta feito junto: o `fx-discover` quebrava com corpo de requisição binário (`UnicodeDecodeError` ao ler `post_data`); agora registra o corpo como ausente e continua.
