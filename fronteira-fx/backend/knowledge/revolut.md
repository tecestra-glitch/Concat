---
title: Revolut (conversor de câmbio)
source: https://www.revolut.com/currency-converter/
tags: provedor, fintech, digital, usd, brl
---
# Revolut (conversor de câmbio)

## O que oferece

Conversor de câmbio da Revolut para USD e BRL, em conta Revolut. O projeto consulta o endpoint JSON do conversor,
porque a página HTML responde com erro 403 a clientes que não são navegador.

## Modalidades

- Conversão USD para BRL e BRL para USD, em conta Revolut. Sem PYG para este provedor no projeto.
- Disponibilidade e região dependem do país e do plano da conta: registrar manualmente, **a confirmar** na conta.

## Horários

- Horário de câmbio em dias úteis e fins de semana: **a confirmar**.
- Há indicação de markup diferente aos fins de semana (ver tarifas): **a confirmar**.

## Tarifas e limites

- O quote público não traz tarifas por plano. Segundo a documentação do adaptador do projeto, planos costumam ter
  franquia mensal sem taxa de câmbio, cobrança percentual acima da franquia e markup em fins de semana.
  Esses valores são **a confirmar** no site ou no aplicativo, para o plano da conta do usuário.
- Fonte pública do conversor: https://www.revolut.com/currency-converter/

## Observações de uso

- O projeto guarda a cotação pública. As taxas do plano devem ser registradas nas configurações da conta; sem elas a
  rota fica com confiança "incompleta".
- O endpoint não é documentado e pode mudar sem aviso.
