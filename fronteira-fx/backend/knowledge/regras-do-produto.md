---
title: Regras do produto (ranking e uso do RAG)
source: interno (docs/api-contract.md, seção "Regras do ranking" e "RAG")
tags: regras, ranking, glossario
---
# Regras do produto (ranking e uso do RAG)

## Ranking das oportunidades

1. Digital com ganho líquido positivo, depois dos custos conhecidos, entra no ranking principal, mesmo com
   microganho.
2. Físico entra no ranking principal só se o ROI físico for pelo menos 0,01 (1 ponto percentual sobre o capital)
   maior que o melhor ROI digital comparável. A comparação vale para o mesmo capital, o mesmo objetivo e o mesmo
   prazo.
3. Quando falta um custo essencial, a confiança é "incompleta". Isso aparece como estimativa incompleta e nunca como
   lucro confirmado.

## O que o RAG pode e não pode fazer

- Pode: trechos de documentação, descrição de provedores, tarifas e limites citados como texto, horários informados
  e trechos de evidência.
- Não pode: cotação, taxa efetiva, ROI, ranking ou qualquer cálculo. Esses valores vêm do banco de dados e do motor.
- Todo trecho citado deve trazer a fonte (campo `source`) e, quando houver, a data em que foi verificado.
- Texto marcado como "a confirmar" nunca é apresentado como fato.
- Tarifa ou limite só entra como fato quando tiver URL oficial e data de verificação. Caso contrário, fica
  como "a confirmar".
- Conteúdo de demonstração (dados ilustrativos) não deve ser colocado na base de conhecimento.
