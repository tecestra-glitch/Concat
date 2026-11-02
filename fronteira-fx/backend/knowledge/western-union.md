---
title: Western Union (BR para PY)
source: https://www.westernunion.com/br/pt/web/send-money/start
tags: provedor, remessa, digital, brl, pyg, simulador
---
# Western Union (BR para PY)

## O que oferece

Envio de dinheiro do Brasil para o Paraguai, com simulador público de preço para o par BRL para PYG.
O preço depende do montante, da forma de pagamento, da forma de recebimento e de promoções.

No fluxo do simulador observado pelo adaptador do projeto em 2026-11-02: destino "Paraguai", pagamento
"PIX ou transferência bancária" e recebimento em "Conta bancária" ou em dinheiro numa loja.

## Modalidades

- Pagamento na origem: PIX ou transferência bancária, como aparece no simulador. Outras formas: **a confirmar**.
- Recebimento no destino: conta bancária ou retirada em dinheiro em loja. Cartão no destino: **a confirmar**.
- Canal: digital (simulador na web). O projeto não tem filial física deste provedor.

## Horários

- O simulador funciona online. Horário de atendimento de suporte ou de agentes: **a confirmar**.
- Prazo de entrega observado no simulador: "0-4 dias úteis" (2026-11-02). Pode variar conforme o recebimento:
  **a confirmar** no simulador antes de cada envio.

## Tarifas e limites

- Taxa e cotação só aparecem no simulador, depois de escolher destino, montante, pagamento e recebimento.
  Não há tabela fixa de tarifas neste documento: **a confirmar** a cada operação.
- Estrutura observada pelo adaptador (2026-11-02, um montante): "taxa de transferência" em BRL, que pode ser 0,00,
  e promoções como "100% de desconto" sobre uma tarifa de referência em BRL. A promoção pode não se repetir.
- Limite de valor por operação e por período: **a confirmar**.
- Fonte pública: https://www.westernunion.com/br/pt/web/send-money/start

## Observações de uso

- A cotação do simulador é indicativa. O valor final só é confirmado no checkout, com login. Nunca tratar o número
  do simulador como valor contratado.
- Cada combinação de montante, pagamento, recebimento, banco e promoção é um contexto diferente. Não misturar
  cotações de contextos diferentes.
- O simulador é uma aplicação de página única. A coleta automática exige navegador e pode quebrar se o site mudar.
  Nesse caso o projeto registra a falha; não inventa valores.
- Para o motor de rotas, a tarifa entra como taxa em BRL. Se ela faltar, a confiança da rota fica "incompleta".
