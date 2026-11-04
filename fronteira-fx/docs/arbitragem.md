# Motor de arbitragem — como funciona

Objetivo: achar qualquer caminho que termine com **mais dinheiro do que começou**, em BRL, USD ou PYG. Pode ser
trocar entre dois bancos, comprar dólar num lugar e vender em outro, ou levar dinheiro vivo de uma cidade para outra.
O ganho só conta se for **líquido**: spread, tarifas, IOF, transferência e deslocamento já descontados.

Regra que não muda: **nada executa movimentação financeira.** O plano só organiza os passos e registra a sua
aprovação e o resultado que você informar.

## Os nós

Um nó é uma moeda num lugar: `USD@chaco:CDE` (dólar na Cambios Chaco, em Ciudad del Este), `BRL@revolut`
(real na conta Revolut), `PYG@cash:FOZ` (guarani em dinheiro vivo em Foz do Iguaçu).

- **Conta**: o saldo livre da sua conta é o ponto de partida dos ciclos.
- **Lugar digital**: banco, fintech ou fonte de cotação online.
- **Casa de câmbio**: `fonte:cidade`, com cotação de balcão.
- **Dinheiro vivo**: `cash:<cidade>`, uma para cada uma das seis cidades (CDE, ASU, PJC, ENC, FOZ e PPO).

## As arestas (cada passo possível)

| Tipo | O que é | Canal |
|---|---|---|
| `quote` (troca) | comprar ou vender numa casa ou banco, pela cotação | presencial (casa) ou assistida (app) |
| `transfer` | mandar dinheiro entre uma conta e um lugar digital, ou uma casa (SIPAP, depósito, Pix) | assistida |
| `deposit` / `withdraw` | levar dinheiro vivo ao balcão ou sacar em ATM | presencial |
| `travel` | ir de uma cidade a outra com o dinheiro | presencial |

Cada aresta tem uma **confiança**: `quoted` (cotação executável), `estimated` (valor estimado) ou `incomplete`.

## Custos

Cada perna mostra quatro custos, sempre na moeda em que a perna começou:

- **spread**: a diferença entre a taxa que você recebe e a taxa de referência (o meio do mercado).
- **fees**: tarifas, fixas ou percentuais.
- **iof**: IOF de conversão quando BRL é convertido fora do Paraguai (banco brasileiro, fintech, Western Union). Sem alíquota conhecida, o IOF fica desconhecido, nunca zero.
- **transport**: custo do deslocamento entre cidades.

Os trilhos (`data/rails.json`) dizem quanto custa cada transferência. As rotas entre cidades (`data/transport.json`)
dizem quanto custa e quanto tempo leva cada deslocamento. Hoje os valores estão **vazios** (`null`) e marcados como
não verificados, até a fase B preencher com fonte.

## Custo desconhecido nunca vira zero

Se faltar um valor (trilho sem tarifa, rota sem custo, IOF sem alíquota, taxa de conversão que não existe), a aresta fica `incomplete`
e o ciclo inteiro também. Um ciclo `incomplete` **não** é "lucro confirmado" e **não** dispara alerta de ganho.

## Ganho em cada moeda

O ganho líquido aparece em BRL, USD e PYG usando as taxas de valoração, que vêm das cotações de referência em BRL
(BCP e as casas). Se uma moeda não tem taxa, o ganho nessa moeda fica vazio (`null`), em vez de zero.

## Fronteira

Uma perna que cruza a fronteira BR↔PY (por exemplo Foz do Iguaçu ↔ Ciudad del Este) é marcada. Se o ciclo leva mais
de **US$ 10 000** por ela, o resultado traz `requires_declaration: true`. É um aviso para você declarar; não bloqueia.

## Planos de execução (sem execução)

Um plano é um ciclo transformado em passos em português:

1. "Leve o dinheiro de CDE para FOZ (≈ 40 min)"
2. "Compre 1.000 USD na Cambios Chaco (CDE) a 7.300 PYG"
3. "Retire 1.000 USD de Cambios Chaco (CDE)"

Fluxo: você cria o plano a partir de um ciclo atual, **aprova** (só grava a decisão), e marca cada passo feito com o
valor que realmente recebeu. Ao concluir o último passo, o resultado (**esperado × realizado**) vai para o diário.

Um plano que ainda não começou **expira** quando a cotação mais velha dele fica velha demais (15 minutos por padrão).
Assim você não executa com uma cotação que já mudou.

## Onde está no código

- Dados: `backend/src/fronteira_fx/data/transport.json`, `data/rails.json`, `services/logistics.py`
- Grafo e custos: `backend/src/fronteira_fx/services/cycles.py`, `engine/graph.py`
- Alertas por ganho líquido: `backend/src/fronteira_fx/services/alerts.py` (`cycle_net_gain`)
- Planos: `backend/src/fronteira_fx/services/plans.py`, rotas em `api/plans.py`
- Contrato completo: `docs/api-contract.md`
