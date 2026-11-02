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
Registro: `registry.py` → `ADAPTERS: dict[str, Adapter]`, `get_adapter(id)`.

## Validação ao vivo (2026-11-02 ~06:07 UTC, domingo→segunda de madrugada em Assunção)

Cada `fetch()` foi executado **uma vez**. Cotações = PYG por 1 unidade da moeda base (compra/venda na perspectiva da casa).

| provider | método | capacidades comprovadas | status observado | valores de amostra (timestamp) | limitações |
|---|---|---|---|---|---|
| `chaco` Cambios Chaco | `official_api` (JSON não documentado: `GET /api/branch_office/` + `GET /api/branch_office/{id}/exchange`; fallback HTML `#main-exchange-content`) | 11 filiais com cidade (ASU×4, CDE×5, PJC×2) → 22 cotações USD/BRL; `updateTs` por filial; mapa de cidades | `STALE` (declarado 2026-10-31T12:04-03:00, 39 h; fim de semana) | chaco-9 (CDE) USD 5810/5920, BRL 1065/1130 @2026-10-31T12:02-03:00; chaco-1 (ASU) USD 5750/5900, BRL 1100/1180 @2026-10-30T13:39-03:00; chaco-28 (PJC) USD 5760/5950, BRL 1080/1140 | API sem contrato público; ~12 requests por coleta (semáforo 4); filiais fora de CDE/ASU/PJC ficam `city=None` |
| `alberdi` Cambios Alberdi | `official_api` (JSON `ws/getTablero.json.php`; fallback HTML `.exchange-table`) | 5 filiais (villamorra=ASU, ciudaddeleste=CDE, km4=CDE, encarnacion, saltodelguaira) → 8 cotações; `timer` = hora declarada (America/Asuncion) | `OK` | villamorra USD 5800/5920, BRL 1070/1155; ciudaddeleste USD 5800/5900, BRL 1070/1120 @2026-11-02T02:07:01-03:00 | Salto del Guairá publica só outras moedas; cross rates (USD→BRL) e cheques ignorados |
| `bonanza` Bonanza Cambios | `official_api` (JSON `GET /api/board` usado pelo SPA React; home é shell de 954 B) | 4 filiais (Casa Matriz=CDE, Jebai=CDE, Paraná Country=None, Asunción=ASU) → 8 cotações; `actualizado` | `STALE` (declarado 2026-10-31T13:02:45Z, 41 h) | matriz USD 5830/5920, BRL 1080/1140; jebai USD 5800/5900, BRL 1080/1160; asuncion USD 5780/5930, BRL 1050/1150 | Não precisou de Playwright: o endpoint responde a HTTP simples; `/api/calcular` (POST origen/destino/monto) existe para conversão |
| `norte` Norte Cambios | `html` (tabela da filial ativa + `wire:snapshot`; outras filiais via replay Livewire `POST /livewire/update setActiveBranch(id)`) | sem bundle: `ERROR` "TLS chain invalid; set FX_NORTE_CA_BUNDLE or allow insecure explicitly" (comprovado). Com `FX_NORTE_CA_BUNDLE` (CAs do sistema + intermediária Sectigo DV R36): PJC + ASU + CDE → 6 cotações | `ERROR` (default) / `STALE` com bundle (latestUpdate 2026-10-31T14:24:14Z, 39,7 h) | norte-1 (PJC) USD 5760/5950, BRL 1080/1140; norte-2 (ASU) USD 5760/5910, BRL 1110/1200; norte-3 (CDE) USD 5770/5950, BRL 1070/1145 | servidor não envia a intermediária → verificação padrão falha; `FX_NORTE_INSECURE=1` desliga a verificação e marca a mensagem; fragmentos Livewire não trazem timestamp (herdam o status da home) |
| `bcp` Banco Central del Paraguay | `html` (`#cotizacion-interbancaria`, data em `#dp_cotizacion`/cabeçalho) | USD e BRL referenciais (`kind=market_reference`), data declarada | `OK` (planilha 30/10/2026; stale só após 4 dias) | USD 5.944,76; BRL 1.100,01 (PYG por unidade) | valor único por moeda: `buy == sell`; dias úteis apenas |
| `ueno` ueno bank | `html` (cards `.divisas-card[data-currency][data-subtitle]`) + AJAX `admin-ajax.php?action=get_fresh_currency_data` (nonce da página) | USD "en tu app" (account/digital) e "en efectivo" (cash/physical); `last_updated` do AJAX | `OK` (nota: "BRL not published on the page") | USD app 5720/6050; USD efectivo 5700/6060 @2026-11-02T02:07:32Z | **BRL não publicado** na página pública (só USD/EUR em 2026-11); sem cidade |
| `nomad` Nomad | `official_api` (`GET https://api.benomad.us/forex-rates-s3/v1/exchanges:90-days`, URL exposta em `data-api` da página) | USD/BRL "dólar comercial" da calculadora pública (`kind=indicative`), histórico 90 d, timestamp | `OK` | USD/BRL 5,4437 @2026-11-02T06:07:01Z | a página **não exibe o spread** da Nomad (só promo "taxa zero na 1ª conversão", "2% de cashback"); proposta efetiva depende da conta — registrar spread manualmente; sem PYG |
| `revolut` Revolut | `official_api` (`GET /api/exchange/quote?...&localeCode=pt-BR`, duas pernas USD→BRL e BRL→USD) | compra = rate(USD→BRL), venda = 1/rate(BRL→USD); timestamp; 403 → `BLOCKED` (testado com respx) | `OK` (ao vivo respondeu 200; a página HTML do conversor dá 403 a clientes não-navegador) | USD/BRL buy 5,419179 / sell 5,457750 @2026-11-02T06:07:11Z (amount 1000) | sem `localeCode` o endpoint devolve 400; taxas por plano/franquia/markup de fim de semana não vêm na resposta; **região/disponibilidade da conta devem ser registradas manualmente** |
| `westernunion` Western Union BR→PY | `browser` (Playwright, Chromium headless) | WU_RESULT_PLACEHOLDER | WU_STATUS_PLACEHOLDER | WU_SAMPLE_PLACEHOLDER | preço vem de `POST /wuconnect/prices/catalog` com fingerprint do navegador (sem request HTTP reproduzível); pix e transferência compartilham o tile "PIX ou transferência bancária"; só o simulador público (valor final só no checkout logado) |

### Western Union — fluxo e evidência

Fluxo observado (pt-BR, 2026-11-02): tile `button[amplitude-id="tile-country-selection"]` "Paraguai" →
`#txtSendAmount` (BRL) / `#wu-currency-select` (PYG) / `#txtReceiveAmount` → tiles de recebimento
`[amplitude-id="tile-fundsout-ba"]` (Conta Bancaria) e `[amplitude-id="tile-fundsout-ag"]` (Receber em dinheiro em uma loja)
→ tile de pagamento `[amplitude-id="tile-fundsin-wupay"]` ("PIX ou transferência bancária") → resumo:
`1.00 BRL = 1,080.3741 PYG`, `100% de desconto 45.00 BRL`, `Taxa de transferência + 0.00 BRL`, `O destinatário recebe 5,401,871.00 PYG`,
`Tempo de atendimento: 0-4 Dias úteis`. Armadilha: o SPA reinicializa o formulário logo depois de renderizar o input
(chamada de limites → "Enviar até 25,000.00 BRL"); um valor digitado antes disso volta a `0.00`. O adapter espera o texto
"Enviar até", digita e confirma que o valor ficou e que os tiles apareceram (até 3 tentativas) antes de clicar.

WU_FLOW_PLACEHOLDER

Screenshots ficam em `backend/var/evidence/wu_<ts>_<amount>_<payment>_<receive>.png` (`backend/var/.gitignore` = `*`).
Fixture histórica `tests/fixtures/westernunion_5000_brl_pyg.json` (5000 BRL, pix, bank_account → 5.401.871 PYG "0–4 dias úteis";
cash_pickup → 5.328.209 PYG "minutos"; promo "100% desconto na tarifa") tem `note`/`historical=true` e `parse()` devolve
`STALE` ("historical fixture data; never current") — nunca é servida como atual. Os testes verificam
taxa efetiva 1080,3742 PYG/BRL = recebido/enviado e que os dois métodos geram cotações e contextos diferentes.

## Variáveis de ambiente

| variável | efeito |
|---|---|
| `FX_NORTE_CA_BUNDLE=/caminho/bundle.pem` | verifica o TLS da Norte Cambios com esse bundle (CAs do sistema + intermediária Sectigo "Public Server Authentication CA DV R36"; o projeto Java `cotizacion` embarca o PEM em `src/main/resources/certs/`) |
| `FX_NORTE_INSECURE=1` | desliga a verificação TLS **só** da Norte, explicitamente; a mensagem do resultado avisa |
| `FX_PW_CHROMIUM=/caminho/chromium` | binário do Chromium para o Playwright quando o download padrão não existe (fallback automático: `/opt/pw-browsers/chromium`) |
| `FX_EVIDENCE_DIR` | diretório das screenshots (default `backend/var/evidence`) |

## Testes

`cd backend && uv run pytest tests/adapters -q` — offline, baseados em fixtures em `tests/fixtures/` (HTML/JSON reais
capturados 2026-10-30..11-02). Cobrem: números concretos por filial/moeda, direção base/quote e `unit_note`, mapa de cidades,
payload vazio / layout alterado → `ERROR`, parcial → `DEGRADED`, timestamp velho → `STALE`, e para `bonanza`/`revolut`
o `fetch()` com respx (200 → OK, 403 → BLOCKED, timeout → ERROR, 500 → ERROR). `uv run ruff check src/fronteira_fx/adapters tests/adapters` limpo.

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
