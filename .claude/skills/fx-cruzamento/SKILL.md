---
name: fx-cruzamento
description: Cruzamento de câmbio entre contas e moedas (BRL, USD, PYG; ueno, Nomad, Revolut, Western Union, casas de câmbio de CDE/ASU/PJC). Monta o grafo de posições (moeda@conta), encontra ciclos e rotas lucrativas a partir do saldo já parado em cada conta, calcula taxa efetiva, ganho líquido e ROI com todos os custos e aplica as regras de ranking do Fronteira FX. Use sempre que o usuário falar em arbitragem, trade de câmbio, "onde está o lucro", comparar remessas ou rotas, spread entre casas, dinheiro parado em várias contas, ou pedir para cruzar cotações, mesmo sem dizer "ciclo" ou "grafo"; também quando houver um JSON ou tabela de cotações para analisar, ou o MCP do Fronteira FX disponível.
---

# fx-cruzamento

Você está ajudando alguém que mantém dinheiro estacionado em várias contas e moedas e quer saber,
a cada momento, **qual troca vale a pena agora**. O trabalho tem três partes: representar tudo como um
grafo, procurar ciclos e rotas com o montante real, e responder de um jeito que não esconda nem exagere
o ganho.

## 1. Represente o problema como grafo de posições

- **Nó** = `MOEDA@venue`. O venue é a conta ou o lugar onde o dinheiro está: `BRL@brbank`, `USD@nomad`,
  `PYG@ueno`, `USD@cash:CDE` (dinheiro físico numa cidade), `PYG@chaco:CDE` (balcão de uma casa de câmbio).
- **Aresta** = uma forma de mover valor entre dois nós, com `taxa` (unidades de destino por 1 de origem),
  `custo_pct` (sobre a entrada), `custo_fixo` (na moeda de saída), `minutos` (prazo), `confianca` e evidência.
  - Cotação de uma fonte vira duas arestas no mesmo venue: a fonte **compra** a moeda base
    (base → cotada, a `compra`) e **vende** (cotada → base, a `1/venda`).
  - Transferência entre contas, saque/depósito e remessa (Pix → Western Union → ueno) são arestas
    com seus próprios custos e prazos. Sem elas o grafo não fecha e nada aparece.
- **Saldo estacionado** = montante disponível em cada nó. Um ciclo só pode começar num nó com saldo; é por
  isso que ter capital em todas as contas muda o problema: não precisa mover dinheiro antes, a
  oportunidade pode começar em qualquer ponta.

Por que não somar logaritmos e pronto? Porque custos fixos e limites por montante dependem do valor que
passa pela aresta. O grafo aqui é pequeno (dezenas de nós), então enumerar ciclos até 6 arestas com o
montante real é mais exato e explica cada etapa. Seis porque um ciclo real entre contas costuma ter
cinco ou seis passos (ex.: BRL@brbank → PYG@ueno → USD@ueno → USD@nomad → BRL@nomad → BRL@brbank);
com 4 só aparecem idas e voltas na mesma casa, que nunca dão lucro. Bellman-Ford fica para grafos grandes.

## 2. Obtenha os dados

Ordem de preferência:

1. **MCP do Fronteira FX** (se conectado): `find_cycles` já devolve ciclos prontos — chame sempre com
   `max_len=6` (o padrão do servidor é 4, que só mostra idas e voltas; 6 é o máximo aceito); `get_quotes`,
   `list_sources` e `compare_routes` trazem cotações com evidência e contexto. Use-os e não recalcule
   o que o motor já calculou. Os campos monetários chegam como strings decimais (`rate`, `gain`, `roi`…):
   trate-os com `Decimal`, nunca como float. `compare_routes` grava uma simulação (`data_mode="simulation"`);
   as demais são só leitura.
2. **JSON ou tabela fornecida pelo usuário**: converta para o formato de `references/formato-entrada.md`
   e rode o script.
3. **Nada disponível**: diga o que falta (cotações, custos de transferência, saldos) e monte o grafo
   só com o que foi dado, marcando o que ficou de fora.

Cuidados que evitam números errados:

- Referência de mercado (BCP, PTAX) **não é executável**: serve como comparação, nunca como aresta.
- Nunca misture contextos de uma cotação (montante, meio de pagamento, forma de recebimento, banco,
  promoção): uma simulação de R$ 5 mil por Pix com retirada em loja não vale para R$ 25 mil em conta.
- Cotação antiga continua antiga mesmo que acabe de ser lida de novo; mostre a idade.
- Dados de demonstração nunca se misturam com dados reais.

## 3. Rode o cálculo com o script

```bash
python3 scripts/cruzar.py entrada.json                 # ciclos, tabela em pt-BR
python3 scripts/cruzar.py entrada.json --json          # saída estruturada
python3 scripts/cruzar.py entrada.json --de BRL@brbank --para PYG@ueno   # rotas abertas (remessa)
python3 scripts/cruzar.py entrada.json --max-arestas 6 --roi-minimo 0
```

O script é determinístico, usa `Decimal` e aplica cada etapa sobre o valor recebido na anterior.
Ele classifica cada ciclo/rota como **digital** ou **presencial** (passa por `cash:` ou balcão) e aplica
o ranking do produto (`references/regras.md`):

- Digital com ganho líquido positivo entra no ranking principal, mesmo que seja um microganho.
- Presencial entra só com ganho positivo **e** ROI ≥ melhor digital comparável + 1 ponto percentual.
- Qualquer aresta com `confianca: incompleta` (custo essencial desconhecido) marca o resultado como
  **estimativa incompleta**: você pode mostrar o número, mas não como lucro confirmado.

## 4. Responda assim

Comece pela conclusão em uma frase: qual troca fazer agora, com qual saldo, e quanto rende. Depois:

1. Tabela em pt-BR (números tabulares; nunca arredonde um microganho para "R$ 0,00": mostre
   `+R$ 0,37` ou `+0,0074 %`). Colunas: início, caminho, saldo usado, ganho, ROI, ROI/dia, prazo, confiança.
2. Para a melhor opção, as etapas uma a uma: de → para, taxa (com a unidade, ex. "PYG por 1 USD"),
   custos, prazo, promoção, evidência.
3. Pendências que impedem chamar de lucro: custos não confirmados, cotações antigas, limites de montante.
4. O que vigiar: os ciclos "quase lá" (ganho ≤ 0 mais próximo de virar positivo) e qual cotação precisaria
   mover.

O que você não faz nesta skill: executar transferências ou compras (a execução é uma fase posterior com
aprovação manual), recomendar automatizar apps de consumidor contra os termos de uso, ou apresentar a
referência do BCP como se fosse uma cotação de balcão.

## Referências

- `references/regras.md`: fórmulas (taxa efetiva, lucro de ciclo, ROI, ROI/dia), regras de ranking e
  classificação digital/presencial, com exemplos numéricos.
- `references/formato-entrada.md`: formato JSON de entrada do script, com um exemplo completo e os
  valores aceitos em cada campo.
