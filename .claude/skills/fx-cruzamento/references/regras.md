# Regras e fórmulas

## Fórmulas

```
taxa efetiva   = crédito líquido recebido ÷ débito total
lucro de ciclo = valor final disponível − capital total alocado
ROI            = lucro líquido ÷ capital total alocado
ROI por dia    = ROI × (1440 ÷ minutos do ciclo)     (mínimo 1 minuto)
```

Cada etapa aplica-se sobre o valor recebido na anterior:

```
saída = entrada × (1 − custo_pct) × taxa − custo_fixo
```

`custo_pct` incide sobre a entrada; `custo_fixo` é descontado na moeda de saída. Uma tarifa nunca é
contada duas vezes: se a promoção zera a tarifa, a aresta tem `custo_fixo: "0"` e a promoção vai na
descrição.

### Exemplo

Ida e volta na mesma casa: US$ 1.000 na ueno. A ueno **compra** USD a ₲ 5.880 (aresta USD@ueno →
PYG@ueno, taxa 5880) e **vende** USD a ₲ 5.940 (aresta PYG@ueno → USD@ueno, taxa 1/5940). Produto das
taxas = 5880/5940 = 0,98990 → ROI −1,01 %: só a ida e volta na mesma casa nunca dá lucro.

Ciclo entre contas (5 arestas): R$ 5.000 no banco BR → Western Union a ₲ 1.101 por R$ 1 = ₲ 5.505.000
na ueno → ueno vende USD a ₲ 5.925 = US$ 929,11 → transferência para a Nomad com 0,2 % = US$ 927,25 →
Nomad compra USD a R$ 5,3950 = R$ 5.002,52 → Pix de volta ao banco. Ganho líquido +R$ 2,52, ROI
+0,05 %, prazo ≈ 3 dias. Lucro aparece quando a compra de uma fonte é maior que a venda de outra
(spread cruzado), descontados custos e prazo; o número é pequeno e precisa ser mostrado como tal.

## Ranking

| Canal | Entra no ranking principal quando |
|---|---|
| digital | ganho líquido > 0 (qualquer valor, inclusive microganho) |
| presencial | ganho líquido > 0 **e** ROI ≥ melhor ROI digital comparável + 0,01 |

"Comparável" = mesmo capital, mesmo objetivo (ciclo, remessa, compra) e prazo parecido. Sem nenhuma
opção digital comparável, o presencial entra só com ganho > 0.

Um resultado é **presencial** se qualquer nó do caminho está em dinheiro físico (`cash:`) ou num balcão
de casa de câmbio (`fonte:cidade`). Operações digitais não recebem cidade inventada.

## Confiança

| Valor | Significado | Como apresentar |
|---|---|---|
| `cotada` | cotação executável/da própria fonte, custos conhecidos | número normal |
| `estimada` | cotação indicativa ou custo estimado | número com "estimado" |
| `incompleta` | custo essencial desconhecido (IOF, tarifa de transferência, encargos do cartão) | "estimativa incompleta", nunca "lucro confirmado" |

O caminho herda a pior confiança das suas arestas.

## Remessa (rota aberta)

Para comparar rotas de A para B (ex.: `BRL@brbank` → `PYG@ueno`), a medida é a **taxa efetiva** do
caminho (saída ÷ entrada), e a economia é a diferença para a referência escolhida (melhor digital, ou
BCP como referência de mercado). A regra do presencial vale do mesmo jeito: a taxa efetiva presencial
precisa superar a melhor digital em ≥ 1 % relativo.
