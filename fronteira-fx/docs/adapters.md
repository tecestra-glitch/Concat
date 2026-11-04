# Adapters de provedores — Fronteira FX

Módulos em `backend/src/fronteira_fx/adapters/`. Todos implementam o protocolo `Adapter` de `base.py`:
`info: AdapterInfo`, `parse(raw, *, captured_at, url, **params)` (puro, usado nos testes com fixtures) e
`async fetch(**params)` (httpx, timeout 20 s, User-Agent de navegador, **sem retries** — o collector faz o backoff).
Nenhum adapter levanta exceção por falha do provedor: devolve `AdapterResult(status, message)`.

Política comum de status (`_common.finalize`):

| situação | status |
|---|---|
| nenhuma cotação parseada (payload vazio, layout mudou, zeros) | `ERROR` com mensagem — nunca zeros silenciosos |
| timestamp declarado mais velho que `stale_after` do adapter | `STALE` (cotações mantidas para o collector gravar como stale) |
| dados parciais (filial/moeda faltando, modalidade desconhecida, fallback HTML) | `DEGRADED` |
| HTTP 401/403/429 ou página de WAF/captcha | `BLOCKED` |
| timeout, TLS, 5xx, JSON inválido | `ERROR` |

Helpers: `_http.py` (UA, timeout, `sha256_hex`, `excerpt`/`build_evidence`, `parse_decimal(text, locale_hint)` para
`"7.350,00"` / `"7,350"` / `"7350"` / `"5.4043"` / `"Gs. 5.680"`, `http_get`/`http_post` com classificação de erros) e
`_common.py` (`BranchInfo`, `city_from_text` → `CDE|ASU|PJC|None`, `finalize`, `quotes_excerpt`).
Registro: `registry.py` → `ADAPTERS: dict[str, Adapter]` (12 adaptadores, **ordenados por id**: a API e o collector
enumeram as fontes nessa ordem), `get_adapter(id)`.

Vocabulário de `QuoteDraft` (`base.py`): `modality` inclui `reference` e `channel` inclui `aggregator` — os dois marcam
cotações de agregador de terceiro (dolarPy), que **nunca** são preço executável nem de balcão e ficam fora do ranking e
do grafo (filtro no backend-core). `_http.looks_blocked` reconhece desafio de WAF pelo que a página **diz**
("Just a moment", "Attention Required", "verify you are human", "complete the captcha", `cf-chl`…) e por 401/403/429;
a palavra "captcha" sozinha não bloqueia, porque páginas legítimas (MaxiCambios, formulários de contato) embutem o badge
do reCAPTCHA v3, o `recaptcha/api.js` e o widget `g-recaptcha` sem serem um desafio.

## Validação ao vivo (2026-11-02 ~06:07 UTC, domingo→segunda de madrugada em Assunção)

Cada `fetch()` foi executado **uma vez**. Cotações = PYG por 1 unidade da moeda base (compra/venda na perspectiva da casa).

| provider | método | capacidades comprovadas | status observado | valores de amostra (timestamp) | limitações |
|---|---|---|---|---|---|
| `chaco` Cambios Chaco | `official_api` (JSON não documentado: `GET /api/branch_office/` + `GET /api/branch_office/{id}/exchange`; fallback HTML `#main-exchange-content`) | 11 filiais com cidade (ASU×4, CDE×5, PJC×2) → 22 cotações USD/BRL; `updateTs` por filial; mapa de cidades | `STALE` (declarado 2026-10-31T12:04-03:00, 39 h; fim de semana) | chaco-9 (CDE) USD 5810/5920, BRL 1065/1130 @2026-10-31T12:02-03:00; chaco-1 (ASU) USD 5750/5900, BRL 1100/1180 @2026-10-30T13:39-03:00; chaco-28 (PJC) USD 5760/5950, BRL 1080/1140 | API sem contrato público; ~12 requests por coleta (semáforo 4); filiais fora de CDE/ASU/PJC ficam `city=None` |
| `alberdi` Cambios Alberdi | `official_api` (JSON `ws/getTablero.json.php`; fallback HTML `.exchange-table`) | 5 filiais (villamorra=ASU, ciudaddeleste=CDE, km4=CDE, encarnacion, saltodelguaira) → 8 cotações; `timer` = hora declarada (America/Asuncion) | `OK` | villamorra USD 5800/5920, BRL 1070/1155; ciudaddeleste USD 5800/5900, BRL 1070/1120 @2026-11-02T02:07:01-03:00 | Salto del Guairá publica só outras moedas; cross rates (USD→BRL) e cheques ignorados |
| `bonanza` Bonanza Cambios | `official_api` (JSON `GET /api/board` usado pelo SPA React; home é shell de 954 B) | 4 filiais (Casa Matriz=CDE, Jebai=CDE, Paraná Country=None, Asunción=ASU) → 8 cotações; `actualizado` | `STALE` (declarado 2026-10-31T13:02:45Z, 41 h) | matriz USD 5830/5920, BRL 1080/1140; jebai USD 5800/5900, BRL 1080/1160; asuncion USD 5780/5930, BRL 1050/1150 | Não precisou de Playwright: o endpoint responde a HTTP simples; `/api/calcular` (POST origen/destino/monto) existe para conversão |
| `norte` Norte Cambios | `html` (tabela da filial ativa + `wire:snapshot`; outras filiais via replay Livewire `POST /livewire/update setActiveBranch(id)`) | sem bundle: `ERROR` "TLS chain invalid; set FX_NORTE_CA_BUNDLE or allow insecure explicitly" (comprovado). Com `FX_NORTE_CA_BUNDLE` (CAs do sistema + intermediária Sectigo DV R36): PJC + ASU + CDE → 6 cotações | `ERROR` (default) / `STALE` com bundle (latestUpdate 2026-10-31T14:24:14Z, 39,7 h) | norte-1 (PJC) USD 5760/5950, BRL 1080/1140; norte-2 (ASU) USD 5760/5910, BRL 1110/1200; norte-3 (CDE) USD 5770/5950, BRL 1070/1145 | servidor não envia a intermediária → verificação padrão falha; `FX_NORTE_INSECURE=1` desliga a verificação e marca a mensagem; fragmentos Livewire não trazem timestamp (herdam o status da home) |
| `bcp` Banco Central del Paraguay | `official_api` (Frankfurter `GET https://api.frankfurter.dev/v2/providers/bcp/rates?base=USD&quotes=PYG` e `?base=BRL&quotes=PYG`, sem chave; parâmetro é `quotes`, não `symbols`) com fallback HTML `#cotizacion-interbancaria` (td[3] = ₲ por unidade; td[2] é ME/USD e **não** deve ser lido) | USD e BRL referenciais (`kind=market_reference`), `declared_updated_at` = `date`; BRL/PYG derivado de USD/PYG ÷ USD/BRL se a perna BRL faltar | `OK` (JSON verificado 2026-11-02: `[{"date":"2026-10-30","base":"USD","quote":"PYG","rate":5944.76}]`; HTML ao vivo também `OK`, planilha 30/10/2026; stale só após 4 dias) | USD/PYG 5944,76; BRL/PYG 1100,01; USD/BRL 5,4043 (data 2026-10-30) | valor único por moeda: `buy == sell`; dias úteis apenas; o feed é um espelho de terceiro (Frankfurter) — se cair, usa bcp.gov.py |
| `ueno` ueno bank | `html` (cards `.divisas-card[data-currency][data-subtitle]`) + AJAX `admin-ajax.php?action=get_fresh_currency_data` (nonce da página) | USD "en tu app" (account/digital) e "en efectivo" (cash/physical); `last_updated` do AJAX | `OK` (nota: "BRL not published on the page") | USD app 5720/6050; USD efectivo 5700/6060 @2026-11-02T02:07:32Z | **BRL não publicado** na página pública (só USD/EUR em 2026-11); sem cidade |
| `nomad` Nomad | `official_api` (`GET https://api.benomad.us/forex-rates-s3/v1/exchanges:90-days`, URL exposta em `data-api` da página) | USD/BRL "dólar comercial" da calculadora pública (`kind=indicative`), histórico 90 d, timestamp | `OK` | USD/BRL 5,4437 @2026-11-02T06:07:01Z | a página **não exibe o spread** da Nomad (só promo "taxa zero na 1ª conversão", "2% de cashback"); proposta efetiva depende da conta — registrar spread manualmente; sem PYG |
| `revolut` Revolut | `official_api` (`GET /api/exchange/quote?...&localeCode=pt-BR`, duas pernas USD→BRL e BRL→USD) | compra = rate(USD→BRL), venda = 1/rate(BRL→USD); timestamp; 403 → `BLOCKED` (testado com respx) | `OK` (ao vivo respondeu 200; a página HTML do conversor dá 403 a clientes não-navegador) | USD/BRL buy 5,419179 / sell 5,457750 @2026-11-02T06:07:11Z (amount 1000) | sem `localeCode` o endpoint devolve 400; taxas por plano/franquia/markup de fim de semana não vêm na resposta; **região/disponibilidade da conta devem ser registradas manualmente** |
| `westernunion` Western Union BR→PY | `browser` (Playwright, Chromium headless) | fluxo completo 5000 BRL → PY (pix / bank_account **e** pix / cash_pickup): valor recebido, taxa exibida, tarifa, desconto promo, prazo; screenshot full-page como evidência; contexto completo em `QuoteDraft.context` | `OK` nas duas execuções finais (06:15–06:16 UTC, 35 s e 33 s cada). Antes disso 3 execuções deram `DEGRADED` (ver abaixo) — nunca números inventados | bank_account: recebe 5.401.871,00 PYG → **1080,3742 PYG/BRL**, tarifa 0,00 BRL ("100% de desconto 45.00 BRL"), "0-4 Dias úteis", taxa exibida 1,080.3741. cash_pickup: 5.328.209,00 PYG → **1065,6418 PYG/BRL**, "Em minutos", promo "100% de desconto 55.00 BRL" (tarifa pós-desconto não capturada no texto desse cenário → `fees=[]`) | preço vem de `POST /wuconnect/prices/catalog` com fingerprint do navegador (sem request HTTP reproduzível); pix e transferência compartilham o tile "PIX ou transferência bancária"; só o simulador público (valor final só no checkout logado) |

### Western Union — fluxo e evidência

Fluxo observado (pt-BR, 2026-11-02): tile `button[amplitude-id="tile-country-selection"]` "Paraguai" →
`#txtSendAmount` (BRL) / `#wu-currency-select` (PYG) / `#txtReceiveAmount` → tiles de recebimento
`[amplitude-id="tile-fundsout-ba"]` (Conta Bancaria) e `[amplitude-id="tile-fundsout-ag"]` (Receber em dinheiro em uma loja)
→ tile de pagamento `[amplitude-id="tile-fundsin-wupay"]` ("PIX ou transferência bancária") → resumo:
`1.00 BRL = 1,080.3741 PYG`, `100% de desconto 45.00 BRL`, `Taxa de transferência + 0.00 BRL`, `O destinatário recebe 5,401,871.00 PYG`,
`Tempo de atendimento: 0-4 Dias úteis`. Armadilha: o SPA reinicializa o formulário logo depois de renderizar o input
(chamada de limites → "Enviar até 25,000.00 BRL"); um valor digitado antes disso volta a `0.00`. O adapter espera o texto
"Enviar até", digita e confirma que o valor ficou e que os tiles apareceram (até 3 tentativas) antes de clicar.

Histórico das execuções do adapter (headless Chromium `/opt/pw-browsers/chromium`, locale pt-BR):

| tentativa | resultado | causa / correção |
|---|---|---|
| 1–2 (06:05) | `DEGRADED` "payment option not offered" / "receive option not found" | o valor digitado voltava a `0.00`: o SPA reinicializa o formulário após a chamada de limites → corrigido esperando "Enviar até" e confirmando que o valor ficou (até 3 tentativas) |
| 3 (06:10) | `DEGRADED` "payment option for 'pix' not offered" (screenshot: formulário zerado) | o clique no tile de recebimento recém-renderizado era perdido → corrigido com 2,5 s de assentamento e re-clique quando os tiles de pagamento não aparecem em 5 s |
| 4 (06:15) | `OK` bank_account **e** cash_pickup | screenshots `backend/var/evidence/wu_20261102T061540Z_5000_pix_bank_account.png` e `wu_20261102T061614Z_5000_pix_cash_pickup.png` |

Blocos conhecidos: o site carrega Akamai Bot Manager (POST `/M2yvHc/...`) e Quantum Metric; nesta sessão não houve bloqueio,
mas um 403/captcha na página inicial devolve `BLOCKED`. `card` só é selecionável se o tile `tile-fundsin-cc/dc` existir
(não apareceu para BR→PY sem login).

Screenshots ficam em `backend/var/evidence/wu_<ts>_<amount>_<payment>_<receive>.png` (`backend/var/.gitignore` = `*`).
Fixture histórica `tests/fixtures/westernunion_5000_brl_pyg.json` (5000 BRL, pix, bank_account → 5.401.871 PYG "0–4 dias úteis";
cash_pickup → 5.328.209 PYG "minutos"; promo "100% desconto na tarifa") tem `note`/`historical=true` e `parse()` devolve
`STALE` ("historical fixture data; never current") — nunca é servida como atual. Os testes verificam
taxa efetiva 1080,3742 PYG/BRL = recebido/enviado e que os dois métodos geram cotações e contextos diferentes.

## MaxiCambios, M&D Cambios e dolarPy (adicionados 2026-11-02)

Os três foram construídos sobre **capturas offline** de 2026-10-30/31 (`backend/tests/adapters/fixtures/`), não sobre
`fetch()` ao vivo: a primeira sondagem real pode voltar `DEGRADED` se a página tiver mudado desde a captura, e isso é o
comportamento esperado (nunca números inventados). Nenhum deles martela: um `GET` por coleta, piso de 60 s no collector.

### `maxicambios` — MaxiCambios (ASU)

- URL: `https://www.maxicambios.com.py/` (`method="html"`; `AdapterInfo.method` não tem valor `http`, `html` é o equivalente).
  Página Angular cujo HTML já vem renderizado pelo servidor — HTTP simples basta, sem Playwright.
- Seletores: quadro principal `#cotizacion-carousel` (Assunção, casa central) com um card `.cotizDivSmall` por moeda:
  `img src=".../flags/<ISO>.png"` identifica a moeda, `<p>Compra</p><p>5700</p>` e `<p>Venta</p><p>5950</p>` trazem os
  valores (es_PY). Cruzado opcional em `#cotizacion-arbi`, coluna cujo `#header-title-board` diz "ASUNCIÓN": o card com
  bandeiras BRL+USD é "Real x Dólar" = **BRL por 1 USD** (`4.85`/`5.40`, ponto decimal — nunca 485). Rodapé
  `* Ultima actualización: 31/10/2026 - 12:10.` (America/Asuncion) → `declared_updated_at`; `stale_after` 72 h (fim de semana).
- Saída: USD/PYG e BRL/PYG com `context={"board":"principal"}`, `branch_id="maxicambios-asu"`; cruzado USD/BRL com
  `context={"board":"arbitraje","pair":"Real x Dólar"}`. Fixture: USD 5700/5950, BRL 1100/1180, cruzado 4.85/5.40.
- Status: cards ausentes (`.cotizDivSmall` sumiu) → `DEGRADED` com evidência; card USD faltando → `DEGRADED` "missing USD";
  timestamp ilegível → `DEGRADED`; 403 ou página de captcha → `BLOCKED`; timeout/5xx → `ERROR`; JSON/vazio → `ERROR`.
- Limitações: só o quadro principal (CDE `#cotizacion-cd`, cheques `#cotizacion-cheq-tra` e a cópia mobile `-xs` não são
  lidos); cotação de balcão indicativa; cruzado ausente vira nota, não degradação.

### `myd` — M&D Cambios (ASU, CDE)

- URL: `https://www.mydcambios.com.py/` (`method="html"`), página renderizada no servidor.
- Seletores: blocos `.cambios-banner-wrap` com `<h2>Asuncion</h2>` → `ASU` e `<h2>CDE</h2>` → `CDE` (há três cópias de
  cada quadro para desktop/mobile, uma delas com `<h2 class="black">`; o adapter lê a primeira por cidade). Linhas
  `.cambios-banner-text ul > li`: `li[0] img` é a bandeira, `li[1]` compra, `li[2]` venda (ícone `<i>` de tendência ignorado).
- Moeda só pelo **nome do arquivo** da bandeira (não há ISO): `us-1.png` = USD, `br.png` = BRL (quadro CDE),
  `descarga.png` = BRL (quadro ASU). Por isso cada valor passa por faixa de plausibilidade (USD 3000–15000, BRL 500–3000
  PYG por unidade): fora da faixa → `DEGRADED` "implausible" e a linha é descartada. Linhas `0` = moeda não negociada.
- Saída: 4 cotações `cash/indicative/physical`, `branch_id="myd-asu"|"myd-cde"`, `context={"section":"<h2>"}`,
  `declared_updated_at=None` (a página não publica horário; a idade vem do hash de conteúdo no collector).
  Fixture: CDE USD 5820/5890, CDE BRL 1080/1115, ASU USD 5780/5930, ASU BRL 1070/1170.
- Status: blocos ausentes → `DEGRADED` com evidência; cidade ou moeda faltando → `DEGRADED`; 403/captcha → `BLOCKED`;
  timeout → `ERROR`.

### `dolarpy` — dolarPy (agregador; **referência, nunca executável**)

- URL: `https://dolar.melizeche.com/api/1.0/` (`method="official_api"`, JSON sem chave):
  `{"dolarpy": {"bcp": {compra, venta, referencial_diario}, "maxicambios": {compra, venta}, "mydcambios": …}, "updated": "2026-10-30 20:50:24"}`.
- Saída: **uma `QuoteDraft` por casa** (14 na captura), USD/PYG, `modality="reference"`, `channel="aggregator"`,
  `kind="market_reference"`, `city=None`, `branch_id="dolarpy-<casa>"`, `context={"aggregator":"dolarpy","house":"<casa>"}`,
  `unit_note` dizendo "referência de terceiro, não executável". `referencial_diario` do BCP é ignorado (o adapter `bcp`
  é o dono desse número). Fixture: maxicambios 5700/5950, bcp 5908.35/5922.67.
- `updated` é hora local do agregador (America/Asuncion); mais de **24 h** → `STALE` (cotações mantidas); `updated`
  ausente/ilegível → `DEGRADED`; casa com entrada quebrada → `DEGRADED` sem derrubar as demais; JSON inválido, HTML,
  lista, `dolarpy` vazio ou só zeros → `ERROR`; 403 → `BLOCKED`. O relógio é injetável (`DolarPyAdapter(clock=...)`) para
  os testes de staleness.
- **dolarPy é referência de terceiro.** Nunca vira preço executável nem cotação de balcão da casa, nunca entra no ranking
  nem no grafo de posições (filtro de `modality="reference"` no backend-core): serve para cruzar com os nossos adapters
  e para cobrir casas que não raspamos. `AdapterInfo.kind="fintech"` porque `SourceKind` não tem valor para agregador.

## Variáveis de ambiente

| variável | efeito |
|---|---|
| `FX_NORTE_CA_BUNDLE=/caminho/bundle.pem` | verifica o TLS da Norte Cambios com esse bundle (CAs do sistema + intermediária Sectigo "Public Server Authentication CA DV R36"; o projeto Java `cotizacion` embarca o PEM em `src/main/resources/certs/`) |
| `FX_NORTE_INSECURE=1` | desliga a verificação TLS **só** da Norte, explicitamente; a mensagem do resultado avisa |
| `FX_PW_CHROMIUM=/caminho/chromium` | binário do Chromium para o Playwright quando o download padrão não existe (fallback automático: `/opt/pw-browsers/chromium`) |
| `EVIDENCE_DIR` | diretório das screenshots e do HTML bruto (default `backend/var/evidence`); `FX_EVIDENCE_DIR` é alias legado (aviso de obsoleto no arranque) |

`backend/var/` inteiro é ignorado por `backend/.gitignore` (`var/`); um `backend/var/.gitignore` local não é versionado.

## Testes

`cd backend && uv run pytest tests/adapters -q` — offline, baseados em fixtures em `tests/fixtures/` (HTML/JSON reais
capturados 2026-10-30..11-02) e, para os três adaptadores de 2026-11-02, em `tests/adapters/fixtures/`
(`maxicambios.html`, `myd.html`, `dolarpy.json`). Cobrem: números concretos por filial/moeda, direção base/quote e `unit_note`, mapa de cidades,
payload vazio / layout alterado → `ERROR`, parcial → `DEGRADED`, timestamp velho → `STALE`, e para `bonanza`/`revolut`/`maxicambios`/`myd`/`dolarpy`
o `fetch()` com respx (200 → OK, 403/captcha → BLOCKED, HTML sem cards → DEGRADED, timeout → ERROR, 500 → ERROR, `updated` velho → STALE); para `bcp`, Frankfurter preferido, fallback HTML quando o feed falha, e os dois fora → BLOCKED/ERROR. Fixtures: `chaco.json`/`chaco.html`/`chaco_branches.json`, `alberdi.json`/`alberdi.html`, `bonanza.json`/`bonanza_shell.html`, `norte.html`, `bcp.html`/`bcp_frankfurter.json`, `ueno.html`/`ueno_ajax.json`, `nomad.json`, `revolut.json`, `westernunion_5000_brl_pyg.json`. `uv run ruff check src/fronteira_fx/adapters tests/adapters` limpo.

## Dependências pendentes

Nenhuma nova. Playwright já está no extra opcional `browser` (`uv sync --extra browser`); sem ele `westernunion.fetch()`
devolve `DEGRADED` com instrução. `python-dateutil` e `selectolax` (backend **lexbor**; o backend Modest está deprecado
na 1.x) já constam em `pyproject.toml`.

## Pistas para evolução

- Chaco expõe também `main`/`arbitrage` por item (cross rates) e `purchaseTrend`/`saleTrend`.
- Bonanza: `GET /api/board` traz `historico` e `monedasConversor`; `POST /api/calcular {origen, destino, monto}`.
- Norte: o `wire:snapshot` traz `text` com o quadro completo em texto (útil como evidência humana).
- Western Union: `POST https://www.westernunion.com/wuconnect/prices/catalog` (body `sender{cty_iso2_ext:"BR",curr_iso3:"BRL",
  send_amount}`, `receiver{cty_iso2_ext:"PY",curr_iso3:"PYG"}`, `visitor{fingerprint_id}`) devolve `services_groups[].pay_groups[]`
  com os preços por combinação fund_in/fund_out; exige fingerprint/cookies da sessão — candidato a adapter HTTP se se provar estável.
- ueno: o AJAX devolve também EUR; se a página passar a publicar BRL, o adapter o captura sem mudanças.

## Extensão PJC/ENC (2026-11-04)

- **Cidade `ENC` (Encarnación)** entrou em `City` (`adapters/base.py`, `schemas.py`, `schemas_candles.py`; `_common.city_from_text`
  reconhece "Encarnación", "ENC" e "ENC." com ponto). Filiais com `city="ENC"`: `chaco-23` (Super 6), `chaco-24` (Mcal. Estigarribia),
  `alberdi-encarnacion`. Salto del Guairá segue `city=None` (fora das seis cidades rastreadas). Chaco passou a sondar as filiais ENC
  (`default_branch_ids`), o que adiciona 2 requisições por coleta.
- **Cruzamentos USD•BRL** (`QuoteDraft` com `base="USD"`, `quote="BRL"`, `unit_note="BRL por 1 USD ..."`, `context={"board": ..., "pair": "USD x BRL"}`,
  canal `physical`, cidade da filial). Compra = o que a casa paga por USD em BRL, venda = o que cobra:
  - `alberdi`: linha `bcp == "USD -> BRL"` (cheques excluídos; zero = sem cotação).
  - `chaco`: nos itens BRL com `arbitrage` truthy, `purchaseArbitrage`/`saleArbitrage` (BRL por 1 USD).
  - `norte`: linha do quadro com rótulo `BRL•USD` (último `span`, versão mobile). Os demais cruzamentos (EUR, ARS) seguem ignorados.
- **Norte Cambios**: a matriz em Pedro Juan Caballero já é `norte-1` com `city="PJC"`; nada a alterar.
- **Ceteg Cambios (PJC)**: não criado. A página só renderiza as cotações via `GET /cotizacion/api?idsucursal=<id>`, e essa
  chamada responde 403 "Acceso no autorizado" a um cliente não autenticado (uma única tentativa, sem retry, sem cookies de sessão).
  Não há restrição explícita de automação nos termos (o link "Términos y Condiciones" é `#`; robots.txt retorna 404), mas o
  acesso é negado pelo próprio site, então o adaptador não contorna esse controle. Revisitar se a Ceteg publicar uma fonte pública.

## Requisições condicionais (2026-11-04)

- `alberdi`: a sondagem agendada faz GET condicional de `ws/getTablero.json.php` (`conditional_get`, `conditional_url`); um 304 não é parseado.
- `maxicambios` e `myd`: GET condicional de `info.url` (HTML renderizado no servidor).
- `chaco` e `norte` **ainda não** têm requisição condicional. A Chaco faz uma requisição por filial (`/api/branch_office/{id}/exchange`) e a Norte troca de filial por `POST /livewire/update`; o watch guarda um único par ETag/Last-Modified por fonte, então um 304 não cobriria as demais requisições. Pendente: validadores por URL (migração de `watch_states`).
