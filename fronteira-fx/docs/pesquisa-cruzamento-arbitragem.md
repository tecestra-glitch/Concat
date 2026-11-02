# Pesquisa: motores de cruzamento e arbitragem para o Fronteira FX

Data da pesquisa: 2026-11-02. Métricas de repositório (estrelas, último push, issues+PRs abertos, licença) obtidas via API do GitHub no mesmo dia. Objetivo do dono do projeto: manter capital estacionado em **todas** as contas (Revolut, Nomad, ueno, Western Union, casas de câmbio) e executar trocas ao vivo sempre que surgir uma oportunidade — detecção contínua de ciclos lucrativos entre moedas, contas e praças (BRL/USD/PYG), com execução aprovada e, depois, automática.

Nota de honestidade: nenhum projeto encontrado resolve exatamente "arbitragem fiat entre fintechs de varejo e casas de câmbio de fronteira". Tudo abaixo vem do mundo cripto/DEX ou de pesquisa acadêmica e precisa ser adaptado. Onde algo não existe (API pública da ueno, da Nomad, open banking paraguaio), está dito explicitamente.

---

## 1. Motores de arbitragem / detecção de oportunidades (open source)

### Top 5 (nota de saúde 0–100 = atividade + licença + modelagem de taxas + multi-venue + linguagem)

| # | Projeto | Licença | Saúde | Linguagem | Métricas (2026-11-02) | O que vale pegar |
|---|---|---|---|---|---|---|
| 1 | **ccxt/ccxt** — https://github.com/ccxt/ccxt | MIT | **95** | Python/TS (+ outras) | 44.672 ★, push 2026-11-02, 754 issues+PRs | Não é um motor de arbitragem, é a *camada unificada de venues* (fetchTicker, fetchOrderBook, createOrder, fees em `exchange.fees['trading']`). É a abstração a copiar para o nosso `Adapter` (cada casa de câmbio / fintech vira um "exchange" com `fetch_quote`, `fees`, `limits`). Dá acesso direto a Bitso e Mercado Bitcoin para o conector cripto futuro (https://docs.ccxt.com/exchanges/bitso). |
| 2 | **hummingbot/hummingbot** — https://github.com/hummingbot/hummingbot | Apache-2.0 | **88** | Python (Cython) | 20.904 ★, push 2026-10-20, 193 abertos | `hummingbot/strategy_v2/executors/arbitrage_executor/arbitrage_executor.py`: executor de arbitragem entre dois mercados que (a) valida saldo antes de abrir (`validate_sufficient_balance` → `CloseType.INSUFFICIENT_BALANCE`), (b) calcula lucro **líquido de taxas** (`_current_profitability = (pnl*amount − tx_cost)/amount`), (c) só executa acima de `min_profitability`, (d) rastreia ordens com `TrackedOrder` e tenta de novo até `max_retries`, (e) normaliza cotações entre moedas de cotação diferentes via `RateOracle`. Também `hummingbot/core/utils/kill_switch.py` (`ActiveKillSwitch`: desliga ao atingir perda/lucro percentual). Docs: https://hummingbot.org/strategies/v2-strategies/executors/arbitrage-executor/ e https://hummingbot.org/client/global-configs/kill-switch/ |
| 3 | **wardbradt/peregrine** — https://github.com/wardbradt/peregrine | MIT | **45** (arquivado em 2021) | Python | 1.249 ★, push 2021-06-28, 8 abertos, **archived** | O melhor código "pequeno" para portar. `peregrinearb/bellmannx.py` (`NegativeWeightFinder.bellman_ford`, `_retrace_negative_cycle`, `NegativeWeightDepthFinder` que limita o volume do ciclo pela profundidade de cada aresta, `calculate_profit_ratio_for_path`) e `peregrinearb/utils/multi_exchange.py` (`create_weighted_multi_exchange_digraph`: multigrafo dirigido em que cada aresta tem `weight = −log(fee_scalar × bid)`, `exchange_name`, `market_name`; taxas por venue via `fee_scalar = 1 − fee`). README sugere Johnson (1975) para enumerar ciclos em vez de achar "qualquer" ciclo. |
| 4 | **bcc-research/CFMMRouter.jl** — https://github.com/bcc-research/CFMMRouter.jl | MIT | **60** | Julia | 363 ★, push 2026-01-01, 3 abertos | Referência de *roteamento ótimo* (não só detecção): formula o problema como otimização convexa com taxas e liquidez por venue, decidindo quanto mandar por cada rota. Base teórica: Angeris et al., "Optimal Routing for Constant Function Market Makers" (https://arxiv.org/abs/2204.05238). Útil quando houver limites por ordem (ex.: Nomad máx. por dia, WU máx. por envio) e for preciso dividir o capital em várias rotas. |
| 5 | **Drakkar-Software/Triangular-Arbitrage** (OctoBot) — https://github.com/Drakkar-Software/Triangular-Arbitrage | **AGPL-3.0** | **55** | Python | 145 ★, push 2025-12-12, 5 abertos | Detector de ciclos multi-ativo sobre ccxt, mantido, mas o README admite: "the results do not account for fees during trades". Licença AGPL impede copiar código para um produto fechado; usar só como referência de estrutura (`run_detection`, whitelist/ignore de símbolos). |

Outros avaliados e descartados ou secundários:

- **maxme/bitcoin-arbitrage** (MIT, 2.589 ★, push 2024-10-20) — https://github.com/maxme/bitcoin-arbitrage — esqueleto clássico de *observer pattern* (um observador loga, outro executa); só spread entre dois mercados, sem grafo.
- **guldo111/triangular-arbitrage-bot-multi-exchange** (MIT, 60 ★, 2023) — https://github.com/guldo111/triangular-arbitrage-bot-multi-exchange — considera taxas, *tick size* e impacto no livro; monolítico, sem testes.
- Sem licença (não copiar, só ler): **herniqeu/graph-arbitrage** (21 ★) https://github.com/herniqeu/graph-arbitrage ; **d-roizman/Bellman-Ford-currency-arbitrage** https://github.com/d-roizman/bellman-ford-currency-arbitrage ; **SUKANT007/Arbitrage-Finder** https://github.com/SUKANT007/Arbitrage-Finder ; **kcmoffat/bellman-ford-forex** (Java, 2014) https://github.com/kcmoffat/bellman-ford-forex .
- **Uniswap/smart-order-router** (GPL-3.0, TS, 519 ★, push 2026-10-22) — https://github.com/Uniswap/smart-order-router — referência de design para *split routing* (divide a ordem por várias rotas e inclui custo de gás por rota ≈ nossas tarifas fixas por transferência). GPL: só referência. **balancer/balancer-sor** está arquivado (https://github.com/balancer/balancer-sor). O Pathfinder da 1inch é proprietário (https://blog.1inch.com/new-pathfinder-algorithm-better-swap-rates) — serve apenas para a ideia de "fundir tokens intermediários antes do último salto" e de incluir custo fixo no roteamento.

### Artigos e papers úteis (ciclos com taxas)

- Robert Martin, "Graph algorithms and currency arbitrage" partes 1 e 2 — https://reasonabledeviations.com/2019/03/02/currency-arbitrage-graphs/ e https://reasonabledeviations.com/2019/04/21/currency-arbitrage-graphs-2/ — a explicação mais clara de nó = moeda, aresta = −log(taxa), ciclo negativo = lucro, com código Python/NetworkX.
- "An Improved Algorithm to Identify More Arbitrage Opportunities on Decentralized Exchanges" — https://arxiv.org/abs/2406.16573 — Bellman-Ford modificado + *line graph* para achar ciclos **a partir de um nó escolhido** e caminhos não-cíclicos A→N (exatamente o nosso caso: começar na conta onde há saldo e terminar em outra moeda/conta).
- "Profit Maximization In Arbitrage Loops" — https://arxiv.org/abs/2406.16600 — otimiza o *valor de entrada* do ciclo (relevante porque casas de câmbio e fintechs têm tarifas fixas + mínimos).
- "Computing Minimum Weight Cycles to Leverage Mispricings in Cryptocurrency Market Networks" — https://arxiv.org/abs/1807.05715 — ciclos de peso mínimo em redes multi-venue.
- "On the Just-In-Time Discovery of Profit-Generating Transactions in DeFi" (DeFiPoser) — https://arxiv.org/abs/2103.02228 — pipeline Bellman-Ford-Moore → validação → execução.

---

## 2. Frameworks de varredura/execução em tempo real: o que emprestar

| Framework | Licença / saúde | O que emprestar para o Fronteira FX |
|---|---|---|
| **Nautilus Trader** — https://github.com/nautechsystems/nautilus_trader | LGPL-3.0, 31.155 ★, Rust+Python, push 2026-11-02 | **RiskEngine** no caminho de submissão: precisão de preço/quantidade, min/max notional, `max_notional_per_order`, impacto no saldo, *rate limit* e estado `ACTIVE/HALTED/REDUCING`; falha gera `OrderDenied` com código padronizado (https://nautilustrader.io/docs/latest/concepts/execution/). `ClientOrderId` nosso (idempotência) vs `VenueOrderId` do provedor, com **reconciliação** no startup; issue #4276 mostra que IDs do venue podem se repetir (https://github.com/nautechsystems/nautilus_trader/issues/4276). LGPL permite uso como biblioteca. |
| **Freqtrade** — https://github.com/freqtrade/freqtrade | GPL-3.0, 56.297 ★, Python | **Dry-run** como modo padrão e **Protections** (`StoplossGuard`, `MaxDrawdown`, `CooldownPeriod`: param de trading por janela de tempo após N perdas ou drawdown) — https://www.freqtrade.io/en/stable/plugins/ . Lição da issue #4837: "stopped trading" precisa deixar claro se bloqueia só entradas ou também saídas (https://github.com/freqtrade/freqtrade/issues/4837). GPL: copiar conceitos, não código. |
| **Hummingbot** — ver §1 | Apache-2.0 | `ArbitrageExecutor` (lucro líquido, saldo, retries), `KillSwitch` por rentabilidade, **Paper Trade** com saldos fictícios por venue (https://hummingbot.org/client/global-configs/paper-trade/). |
| **OctoBot** — https://github.com/Drakkar-Software/OctoBot | GPL-3.0, 6.883 ★ | *Paper trading* e simulador por exchange. Só referência (GPL). |
| **Jesse** — https://github.com/jesse-ai/jesse | MIT, 8.756 ★, push 2026-10-31 | `Strategy` com estados de posição e *paper/live* espelhados; cripto direcional, pouco multi-venue. |
| **QuantConnect Lean** — https://github.com/QuantConnect/Lean | Apache-2.0, 22.342 ★, C# | `BrokerageModel` (taxas, fills, limites por corretora) e estados de ordem `New→Submitted→PartiallyFilled→Filled/Canceled/Invalid`. |

**Máquina de estados de ordem recomendada** (síntese Nautilus + Lean + Hummingbot): `PROPOSED → APPROVED (humano) → SUBMITTED → ACKNOWLEDGED (id do venue) → PARTIALLY_SETTLED → SETTLED | REJECTED | EXPIRED | FAILED | UNKNOWN (requer reconciliação)`. Cada transição grava evento imutável; `UNKNOWN` bloqueia novas entradas até reconciliar saldos.

---

## 3. MCPs e skills para finanças/FX

**Oficiais / primeira parte**

- **Frankfurter MCP** (oficial, remoto, sem chave): `https://mcp.frankfurter.dev/` — ferramentas `convert`, `get_rates`, `list_currencies`, `list_providers` — https://frankfurter.dev/mcp/ . Relevância **alta**: a Frankfurter republica a cotação referencial do **Banco Central del Paraguay** (`provider=bcp`, 26 moedas desde 2001): `https://api.frankfurter.dev/v2/providers/bcp/rates` — https://frankfurter.dev/es/providers/bcp/ . Repositório da API: https://github.com/lineofflight/frankfurter (MIT, 2.052 ★, Ruby, push 2026-10-30).
- **Belvo MCPs** (oficial): *Developer MCP* (docs, aberto) e *Data Access MCP* (saldos/transações via Open Finance Brasil, exige conta Belvo e consentimento do usuário), ambos "live" no Brasil e México — https://belvo.com/resources/mcps/ e https://developers.belvo.com/developer_resources/resources-mcp-server . Relevância alta para **ler saldos BRL**.
- **Binance Skills Hub** (oficial Binance): https://github.com/binance/binance-skills-hub (1.116 ★, push 2026-10-26, sem campo de licença) — inclui skill **p2p** com endpoint público de anúncios (`/bapi/c2c/v1/public/c2c/agent/ad-list`, filtros por fiat/ativo/método de pagamento) — útil para cotar **USDT↔PYG e USDT↔BRL** no P2P sem credenciais.
- **anthropics/skills** (oficial Anthropic): https://github.com/anthropics/skills — não tem skill de trading/FX; serve como padrão de formato `SKILL.md`.
- **Alexandria/Firecrawl** (o servidor `firecrawl` do `.mcp.json` do projeto só sobe com `FIRECRAWL_API_KEY`; em sessões claude.ai as ferramentas Alexandria `mcp__Firecrawl__*` vêm do conector do usuário, não do servidor do projeto): provedores `bcb-gov-br/economic-data/ptax_usd`, `ptax_currency`, `xe-com/exchange-rates/*`, `ecb-europa-eu/fx_rates` — PTAX e XE sem escrever scraper.

**Comunitários**

| MCP / skill | Licença, saúde | Relevância |
|---|---|---|
| doggybee/mcp-server-ccxt — https://github.com/doggybee/mcp-server-ccxt | MIT, 145 ★, TS, push 2025-06 | Alta para fase cripto: tickers/orderbook/ordens em 100+ exchanges (Bitso, MB). Pouco mantido. |
| lazy-dinosaur/ccxt-mcp — https://github.com/lazy-dinosaur/ccxt-mcp | MIT, 95 ★, TS, push 2026-04 | Alternativa mais recente ao anterior. |
| AnalyticAce/binance-mcp-server — https://github.com/AnalyticAce/binance-mcp-server | MIT, 50 ★, Python/FastMCP, push 2026-09 | Spot/futuros Binance; não cobre P2P. |
| gu-does-git/pluggy-mcp — https://github.com/gu-does-git/pluggy-mcp | MIT, 0 ★, TS, 2026-06 | Pluggy **não** tem MCP oficial; este expõe 18 ferramentas da API Pluggy. Baixa maturidade. |
| thunderjr/openfinance-mcp-server — https://github.com/thunderjr/openfinance-mcp-server | sem licença, Go, 2 ★ | Idem, via Pluggy. Sem licença = não copiar. |
| wesbos/currency-conversion-mcp — https://github.com/wesbos/currency-conversion-mcp | sem licença, 37 ★ | Frankfurter embrulhado; redundante. |
| tradermonty/claude-trading-skills — https://github.com/tradermonty/claude-trading-skills | MIT, 3.543 ★, push 2026-11-02 | Ações EUA; só o padrão skill + script interessa. |
| agiprolabs/claude-trading-skills — https://github.com/agiprolabs/claude-trading-skills | MIT, 507 ★ | 68 skills DeFi/quant; molde de skill. Geeksfino/finskills (Apache-2.0) idem, foco em ações. |
| 00xLazy/TradeOS — https://github.com/00xLazy/TradeOS | MIT, 23 ★, TS, push 2026-03 | Skill com "arbitrage scanner net of fees" sobre ccxt e *confirmation gates*; pequeno, mas o desenho (gate de confirmação antes de ordem) é exatamente o nosso modo "aprovado". |

Não existe MCP oficial da **Wise**, **Revolut**, **Nomad** ou **ueno**; as páginas que aparecem em buscas ("revolut business to mcp") são geradores genéricos, não produtos.

**PTAX direto do BCB — referência alternativa (avaliada em 2026-11-02, não instalada)**

- **bcb-br-mcp** — https://github.com/SidneyBissoli/bcb-br-mcp — MIT (código; dados do BCB sob ODbL), npm `bcb-br-mcp@1.19.0` (publicado 2026-10-28), projeto pequeno (cerca de 10 estrelas). Ferramentas `bcb_cambio_cotacao` (PTAX por data e moeda) e `bcb_cambio_moedas`, sem chave, só consulta. É a única lacuna clara da configuração atual: a Frankfurter (já no `.mcp.json`) cobre o BCP, mas não a PTAX direto do BCB para o lado BRL (hoje a PTAX só chega via Alexandria `bcb-gov-br/economic-data/ptax_usd`, que depende do conector Firecrawl). **Não instalado** (nem entrou no `.mcp.json`): fica como referência alternativa. Se for adotado, fixar a versão (`npx -y bcb-br-mcp@1.19.0`, `--scope project`), converter `rate` numérico com `Decimal(str(...))` e tratar o valor como `market_reference` (comparação, nunca aresta executável).
- Descartados nesta rodada: `frankfurtermcp` (PyPI 0.5.0, redundante com o oficial e sem parâmetro `provider`, então não alcança o BCP); `wesbos/currency-conversion-mcp` (sem licença); `cahthuranag/realtime-exchange-rate-mcp` (exige chave, fonte de dados não verificada); `Ruddxxy/currency-exchange-mcp` (versão hospedada paga). Não existe MCP dedicado ao Banco Central del Paraguay; os dados abertos estão em https://www.datos.gov.py/node/843 e `mcp-bcra` / `mcp-uruguay` (PyPI) servem de molde caso um dia valha escrever um.

---

## 4. Conexão de contas (fase de execução — apenas pesquisa)

| Provedor | O que existe | Limites e avisos |
|---|---|---|
| **Revolut Business** | API oficial com `GET /rate` (cotação de venda com taxa esperada) e `POST /exchange` (vender X ou comprar Y entre contas em moedas diferentes; estados `pending/completed/failed`), sandbox em `sandbox-b2b.revolut.com`, produção `b2b.revolut.com/api/1.0` — https://developer.revolut.com/docs/api/business/operations/get-rate.md , https://developer.revolut.com/docs/api/business/operations/exchange-money.md , https://developer.revolut.com/docs/guides/manage-accounts/exchange-money | **Só contas Business.** Conta pessoal não tem API pública; a *Open Banking API* é restrita a TPPs regulados (PSD2/UK) — https://developer.revolut.com/docs/guides/build-banking-apps/introduction-to-the-open-banking-api/introduction.md . Termos anteriores proibiam uso automatizado/scraping do app (https://conductatlas.com/platform/revolut/revolut-terms-of-service-superseded-url/provision/CA-P-034161/prohibition-on-use-harmful-to-revolut-systems/); ler os termos vigentes antes de automatizar. |
| **Wise** (referência) | API com *personal tokens* (Settings → API tokens) que leem a conta, criam cotações (`/v3/profiles/{id}/quotes`) e rascunhos de transferência; endpoint de taxas `GET /v1/rates?source=&target=`; sandbox `api.wise-sandbox.com` — https://docs.wise.com/api-docs/api-reference/quote , https://docs.wise.com/api-docs/api-reference/rate | Financiar transferências por API com token pessoal é limitado (SCA/PSD2 para perfis UE/UK). Bom modelo de "quote → transfer → fund" com cotação travada por tempo. |
| **Nomad** | Nenhuma API pública ou portal de desenvolvedores encontrado — https://openbankingtracker.com/provider/nomadbanking/apis . Página pública de cotação carrega via JavaScript — https://www.nomadglobal.com/cotacoes/dolar | Spread 2% sobre o comercial, progressivo até 1% (Nomad Pass), + IOF — fonte de terceiros (https://passageirodeprimeira.com/spread-zero-nomad-oferece-taxa-de-servico-zerada-para-novos-clientes). **Automatizar o app muito provavelmente viola os termos**; caminho legítimo: Open Finance (se participante) ou operação manual aprovada no terminal. |
| **ueno bank (PY)** | Nenhuma API pública, sandbox ou portal — https://openbankingtracker.com/country/paraguay . A ueno publica cotações no site (raspadas por dolarPy e aVolpe/cotizacion, atrás de Cloudflare) | Nenhuma regulação paraguaia de finanzas abiertas localizada (normas do BCP: https://www.bcp.gov.py/web/institucional/vigentes). Prometeo anunciou expansão ao PY em 2023, sem cobertura confirmada (https://www.descubre.vc/noticia/prometeo-prepara-su-expansi-n-a-paraguay-rep-blica-dominicana-y-costa-rica-2023-10-17); diretórios listam 0 agregadores PY (https://www.openbankingtracker.com/api-aggregators?country=PY). |
| **Open Finance Brasil** (ler saldos BRL) | **Pluggy** (conectores Open Finance, sandbox) — https://docs.pluggy.ai/en/docs/open-finance/overview ; **Belvo** (dados + iniciação de pagamento + MCP) — https://belvo.com/resources/mcps/ ; **Klavi** (Klavi Link + APIs no padrão OFB) — https://docs.klavi.ai/connect/OBPg-overview | Todos B2B: exigem contrato/conta de desenvolvedor e consentimento do titular. É o único caminho **legal e estável** para ler saldos de bancos BR (e de fintechs que participem do OFB). |
| **Western Union** | WU Business Solutions expõe APIs a clientes empresariais (press release 2020) — https://www.nasdaq.com/press-release/western-union-delivers-next-evolution-of-its-open-banking-api-for-global-payments . O suposto portal `wu-priora.saltedge.com` só aparece em diretórios de terceiros, não em domínio WU | Nenhum programa público para pessoa física. Cotações WU continuam via navegador (Playwright), como já está em `docs/api-anything.md`. |
| **Cripto on/off-ramp (futuro)** | **Binance P2P**: endpoint público não documentado `https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search` (fiat=PYG/BRL, asset=USDT) ou o da skill oficial; PYG existe no P2P segundo guias (https://finantres.com/?p=488851). **Bitso**: https://docs.bitso.com/ . **Mercado Bitcoin v4**: https://api.mercadobitcoin.net/api/v4/docs . Ambos no ccxt. | Binance não é entidade regulada no Paraguai; USDT P2P tem risco de contraparte e KYC obrigatório. Tratar como venue de **cotação** primeiro, execução só depois de risco revisado. |

**Aviso direto sobre ToS**: automatizar apps de consumidor (Revolut pessoal, Nomad, ueno, WU) via sessão autenticada ou automação de UI tende a violar os termos e pode bloquear a conta. Desenho correto: (1) cotação pública sem login, (2) saldos por Open Finance/API oficial, (3) execução **manual aprovada** no app enquanto não houver API; automática só em Revolut Business, Wise e exchanges com API.

---

## 5. Fontes de dados

**Paraguai**
- **BCP — cotización referencial** (tabela diária, HTML estático): https://www.bcp.gov.py/webapps/web/cotizacion/monedas . Sem JSON oficial; via **Frankfurter** `https://api.frankfurter.dev/v2/providers/bcp/rates` (histórico desde 2001, CSV).
- **DNIT — cotizaciones** (tabela mensal oficial p/ aduana): https://www.dnit.gov.py/web/portal-institucional/cotizaciones
- **aVolpe/cotizacion** (MIT, Java/Spring + cliente web, push 2026-11-02): coleta a cada 10 min **Cambios Chaco, Cambios Alberdi, MyD, Amambary, MaxiCambios** e já tem geolocalização de agências ueno — API `/api/exchange/` e `/api/exchange/{currency}` — https://github.com/aVolpe/cotizacion , site https://cotizaciones.volpe.com.py/ . É a fonte agregada mais madura do país.
- **melizeche/dolarPy** (Apache-2.0, Python, push 2026-10-30): raspa ~12 fontes (Chaco, Alberdi, MaxiCambios, ueno, BCP…) a cada 10 min; API JSON `http://dolar.melizeche.com/api/1.0/`; testes "live" noturnos que abrem issue quando um site muda — https://github.com/melizeche/dolarPy . Padrão de resiliência que vale copiar nos adaptadores do Fronteira FX.
- **cambios.com.py** — API REST `GET /api/v1/rates/dolar/today` com `X-API-Key`, grátis até 1.000 req/dia, dados DNIT/BCP/casas; frequência de atualização descrita de forma contraditória — https://cambios.com.py/
- Sites de casas (HTML, sem JSON): Cambios Chaco https://www.cambioschaco.com.py/ (mapeado em `docs/api-anything.md`), Santa Rita https://www.santaritacambios.com.py/ .
- **dolarapi.com** (MIT) cobre Brasil e outros, **não** Paraguai — https://github.com/enzonotario/dolarapi.com

**Brasil**
- **PTAX (BCB Olinda, OData + Swagger)**: `https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/` — documentação https://opendata.bcb.gov.br/dataset/american-dollar-bid-and-offer-daily-rates/resource/ccde1793-418d-4231-a334-fa70ffe10373 ; também pelo provedor Alexandria `bcb-gov-br/ptax_usd` já disponível no MCP Firecrawl do projeto.
- **Nomad** (página pública, JS): https://www.nomadglobal.com/cotacoes/dolar — candidato ao `learn` do api-anything.
- **Wise** `GET /v1/rates` (mid-market) — https://docs.wise.com/api-docs/api-reference/rate .

---

## Recomendação de arquitetura para o Fronteira FX

### O que é o "grafo de posições"

Imagine um mapa. Cada **nó** é um lugar onde dinheiro pode estar, escrito como `moeda@conta/praça`: `BRL@pix`, `USD@nomad`, `USD@revolut`, `PYG@ueno`, `USD@cash-CDE`, `PYG@cash-Chaco-CDE`. Cada **aresta** é uma forma de converter ou mover dinheiro entre dois nós, com tudo que custa: `BRL@pix → USD@nomad` (spread 2% + IOF), `USD@revolut → USD@cash-CDE` (saque: tarifa fixa + limite diário), `USD@cash-CDE → PYG@cash-Chaco-CDE` (bid da casa), `PYG@ueno → BRL@pix` (remessa WU: taxa + câmbio). É o que Peregrine faz em `create_weighted_multi_exchange_digraph` (multigrafo dirigido com `exchange_name` por aresta) e o que o Hummingbot chama de "mercado" em cada lado do `ArbitrageExecutor`.

### Por que Bellman-Ford em −log(taxa) encontra ciclos lucrativos

Percorrer um caminho multiplica as taxas: 1 BRL × 0,183 × 5,80 × 0,00095… Algoritmos de caminho mínimo somam pesos, não multiplicam. Troca-se cada taxa `r` por `w = −log(r)`: multiplicar taxas vira somar pesos, e um ciclo cuja multiplicação dá mais que 1 (lucro) vira um ciclo de soma **negativa**. Bellman-Ford é o algoritmo padrão para caminhos mínimos com pesos negativos e, se depois de `|V|−1` relaxamentos ainda houver aresta relaxável, existe ciclo negativo — basta retroceder pelos predecessores (`_retrace_negative_cycle` no Peregrine) para listar as moedas/contas do ciclo. Com ~30 nós e ~150 arestas isso roda em microssegundos; podemos recalcular a cada cotação nova. Referências: https://reasonabledeviations.com/2019/03/02/currency-arbitrage-graphs/ e https://arxiv.org/abs/2406.16573 .

### Por que taxas, mínimos, limites e atrasos têm de ser atributos da aresta

- **Taxa proporcional** (spread, IOF, comissão): entra direto no peso, `w = −log(r × (1 − fee))`, como o `fee_scalar` do Peregrine.
- **Tarifa fixa** (R$ 15 de saque, US$ 5 de envio WU): não cabe em um peso único porque depende do valor; o peso da aresta passa a ser uma **função do montante** `w(x) = −log((r·x − fixo)/x)`. Na prática: calcular o grafo para 4 montantes (5/10/25/50 mil, como o README do projeto já faz) ou usar o truque de "profundidade" do `NegativeWeightDepthFinder` (cada aresta tem o volume máximo em que a cotação vale).
- **Mínimos e limites** (mínimo de envio, teto diário, estoque da casa de câmbio): atributos `min_amount`, `max_amount`, `remaining_daily`; aresta é ignorada fora da faixa. É o que o RiskEngine do Nautilus valida com `min_notional/max_notional`.
- **Tempo de liquidação** (`settle_seconds`: Pix 10 s, WU minutos a horas, Revolut→ATM depende de ir até lá): não entra no peso, mas no **risco**: durante a espera a próxima cotação pode mudar. Guardar `settle_seconds` e `quote_ttl_seconds` por aresta e descontar o lucro por um fator de volatilidade esperada no intervalo (o módulo de volatilidade do frontend já existe).
- **Praça física** (CDE vs Asunción vs PJC): é nó distinto; a aresta entre praças tem custo de deslocamento e tempo — por isso a regra "presencial só entra se ROI ≥ digital + 0,01" faz sentido como atributo de aresta, não como filtro posterior.

### Como "capital estacionado em todas as contas" muda o problema

Nos bots clássicos o ciclo precisa **voltar** à moeda de partida (A→B→C→A) porque o capital está em um só lugar. Aqui o capital já está distribuído, então:

1. **Qualquer nó com saldo é fonte**. Rode Bellman-Ford com uma **super-fonte** virtual ligada a cada `moeda@conta` que tenha saldo (peso 0): um único passe encontra ciclos alcançáveis de qualquer conta — o paper https://arxiv.org/abs/2406.16573 formaliza "ciclo a partir de um nó escolhido".
2. **Caminhos abertos também valem**. Se o objetivo é rebalancear (ex.: precisa de PYG em CDE na sexta), um caminho `USD@revolut → … → PYG@cash-Chaco` que entrega mais PYG que a rota direta é "oportunidade" mesmo sem fechar ciclo. Compare o caminho ótimo com a rota de referência (BCP/PTAX) e registre o ganho relativo.
3. **ROI sobre o saldo usado, não sobre o capital total**: `ROI = (valor final − valor inicial no mesmo numerário) / valor inicial usado`, convertido a BRL pelo PTAX do dia para comparar rotas. Reporte também **ROI anualizado pelo tempo de liquidação** (`ROI × 365 d / dias_para_liquidar`) — um ganho de 0,4% em 20 minutos vale mais que 0,6% em 3 dias com capital travado.
4. **Estoque é restrição**: o volume do ciclo é `min(saldo na fonte, max_amount de cada aresta, estoque da casa)`; o `NegativeWeightDepthFinder` e `get_starting_volume` do Peregrine já implementam exatamente esse mínimo encadeado.
5. **Pós-execução o grafo muda**: saldos movem de nó; recompute e evite a mesma aresta dentro do `quote_ttl`.

### Plano de adoção concreto

**Portar (código MIT, para `backend/src/.../engine/`)**
- `peregrinearb/bellmannx.py` → `graph/negative_cycle.py` (Bellman-Ford, retrace, depth) reescrito em `Decimal` e com super-fonte.
- `peregrinearb/utils/multi_exchange.py` → `graph/builder.py`: monta o multigrafo a partir das cotações normalizadas dos adaptadores (`bid/ask`, `fee_pct`, `fee_fixed`, `min/max`, `settle_seconds`, `quote_ttl`, `place`).
- Padrão de observers de `maxme/bitcoin-arbitrage` (MIT) para `observers/`: `Logger`, `Notifier`, `PaperTrader`, `ApprovalQueue`, `Executor`.
- Lógica do `ArbitrageExecutor` do Hummingbot (Apache-2.0, compatível): `validate_sufficient_balance`, cálculo líquido de taxas, `min_profitability`, `TrackedOrder`, `max_retries`; e `ActiveKillSwitch` (loop de 10 s que para tudo ao cruzar perda-limite).
- Testes "live" noturnos do `dolarPy` (Apache-2.0) para cada adaptador de casa de câmbio, abrindo issue/alerta quando o HTML muda.

**Usar como biblioteca**
- `ccxt` (MIT) para Bitso/Mercado Bitcoin/Binance spot quando a fase cripto chegar; sua estrutura `fees/limits/precision` é o molde do `Adapter` do projeto.
- `nautilus_trader` (LGPL): opcional; se não for usado como lib, copiar só o **contrato** do RiskEngine (lista de validações e códigos de recusa) e o esquema `client_order_id`/`venue_order_id` + reconciliação no boot.
- Frankfurter (API e MCP) para BCP/PTAX/ECB históricos; aVolpe/cotizacion e dolarPy como fontes agregadas de fallback (sempre marcando `source` e `observed_at`).

**MCPs a conectar** (no `.mcp.json`, além dos existentes): `frankfurter` (`https://mcp.frankfurter.dev/`, sem chave); Belvo Data Access MCP (quando houver conta) para saldos BRL via Open Finance; `mcp-server-ccxt` **não**: expõe ordens (tickers/orderbook/ordens), o que contraria a regra de nunca executar movimentação financeira — se a fase cripto chegar, usar `ccxt` como biblioteca, só com chamadas de leitura. O MCP próprio `fronteira-fx` deve ganhar as ferramentas `scan_cycles(min_roi, max_settle_hours, places)`, `explain_cycle(id)`, `propose_execution(id, amount)` e `approve(id)`.

**Controles de risco antes de qualquer execução automática** (todos em `Decimal`, persistidos, com auditoria):
1. Modos em escada: `paper` (saldos fictícios por venue, como o Paper Trade do Hummingbot) → `approve` (toda ordem exige aprovação humana com TTL igual ao `quote_ttl`) → `auto` só por par de venues com API oficial (Revolut Business, Wise, exchanges), nunca para apps de consumidor.
2. Limites: `max_notional_per_order`, `max_notional_per_day`, `max_open_exposure` por moeda e por conta, `max_loss_per_day` (kill switch), `max_orders_per_minute` (rate limit), `min_profit_after_fees` com margem de segurança para slippage.
3. **Validade**: oportunidade expira com a cotação mais antiga do ciclo; ordem não é enviada se qualquer aresta estiver vencida ou se a fonte não atualizar há > N segundos (dado "stale").
4. **Idempotência**: `client_order_id` determinístico (`hash(ciclo, montante, quote_ts)`); reenvio após timeout consulta antes de recriar; estado `UNKNOWN` bloqueia novas entradas até reconciliar saldos com o venue (lição Nautilus/Freqtrade #4837).
5. **Custos desconhecidos → "estimativa incompleta"** (regra já existente no README), nunca lucro confirmado; aresta com `fee=null` recebe peso pessimista.
6. **Kill switch** por perda acumulada, por falhas consecutivas (`max_retries`) e manual (um comando/MCP `halt`), com estado `HALTED` que recusa submissões mas permite cancelamentos e consultas.
7. Registro em diário (`/diario`) de cada ciclo detectado, aprovado, executado e do resultado real vs previsto — a diferença alimenta a calibração de taxas e slippage por venue.

Assim o Fronteira FX evolui de **detector contínuo multi-fonte** (fase 1: dados públicos + saldos informados) para **executor aprovado** (fase 2: Open Finance + aprovação humana) e só então **automático** nos corredores com API oficial (fase 3), sem automação de apps de consumidor.
