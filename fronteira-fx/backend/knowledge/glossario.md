---
title: Glossário do câmbio
source: interno (glossário do produto)
tags: glossario, usd, brl, pyg
---
# Glossário do câmbio

## Taxa efetiva

Quanto a pessoa realmente recebe por unidade enviada, depois de pagar tudo. Numa remessa, a taxa efetiva é o valor
recebido dividido pelo valor enviado (por exemplo, PYG recebidos dividido por BRL enviados). A tarifa aparece à parte,
como o adaptador da Western Union registra. Nas rotas, a taxa efetiva é calculada pelo motor com todas as taxas
conhecidas. Quando falta um custo essencial, a confiança é "incompleta".

## Spread

Diferença entre o preço de compra e o de venda que a casa aplica à mesma moeda. Quanto maior o spread, pior para
quem converte nos dois sentidos. Pode ser dado em valor absoluto (PYG por USD) ou em percentual sobre a referência.
Em várias páginas públicas o spread não aparece e precisa ser registrado manualmente.

## ROI (retorno sobre o capital)

Lucro líquido dividido pelo capital de entrada. Exemplo do contrato do produto: ganho líquido de 42,10 BRL sobre
capital de 5.000 BRL dá ROI de 0,00842, ou 0,842%.

## Ciclo

Sequência de conversões e transferências que volta à moeda inicial, por exemplo BRL para PYG, depois PYG para USD e
USD de volta para BRL. O ciclo dá ganho quando o valor final supera o capital inicial, depois dos custos conhecidos.
O motor avalia os ciclos a partir dos saldos disponíveis.

## Remessa

Envio de dinheiro para outra pessoa ou conta, normalmente por um provedor especializado, como a Western Union. É
diferente de converter dinheiro numa conta própria. Costuma ter tarifa fixa ou percentual, prazo de entrega e
promoções.

## IOF

Imposto sobre Operações Financeiras, que incide sobre operações de câmbio no Brasil. A alíquota e a incidência
dependem do tipo de operação: **a confirmar** antes de usar num cálculo. No produto, um IOF ainda não confirmado
aparece como custo pendente ("IOF confirmar").

## Compra e venda (perspectiva da casa)

Na perspectiva da casa de câmbio, compra é o preço pelo qual ela compra a moeda base, e venda é o preço pelo qual
ela vende. Por isso, quem vende BRL para a casa usa um preço e quem compra BRL da casa usa outro.

## Tipos de cotação

- Referência de mercado: valor de referência, não executável. Exemplo: BCP.
- Indicativa: valor informado pelo provedor, sem garantia de execução.
- Executável: valor que pode ser executado naquele momento. Confirmar sempre no checkout ou no balcão.

## Confiança da rota

- Cotada: valor obtido da fonte.
- Estimada: valor calculado a partir de premissas ou de dados parciais.
- Incompleta: falta um custo essencial. Nunca apresentar como lucro confirmado.

## PYG, USD e BRL

- PYG: guarani paraguaio. Os valores são altos (por exemplo, 7300 PYG por 1 USD, valor de exemplo) e a
  interface usa separador de milhar.
- USD: dólar dos Estados Unidos.
- BRL: real brasileiro.

## Modalidade e canal

- Modalidades: cash (espécie), transfer (transferência), account (conta digital), card_debit, card_credit e
  card_virtual (cartões).
- Canal: digital (sem filial) ou físico (balcão).
- Cidades: CDE (Ciudad del Este), ASU (Asunción) e PJC (Pedro Juan Caballero).
