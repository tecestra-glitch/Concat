# Formato de entrada do `scripts/cruzar.py`

Um único JSON com quatro blocos. Números como **string** (preservam precisão) ou número.

```json
{
  "cotacoes": [
    { "fonte": "ueno", "cidade": null, "base": "USD", "cotada": "PYG",
      "compra": "5880", "venda": "5940", "modalidade": "conta", "tipo": "indicativa",
      "taxas": [], "montante": null, "evidencia": "ev-1", "capturada_em": "2026-11-02T10:00:00Z" },
    { "fonte": "chaco", "cidade": "CDE", "base": "USD", "cotada": "PYG",
      "compra": "5905", "venda": "5975", "modalidade": "dinheiro", "tipo": "indicativa" },
    { "fonte": "bcp", "cidade": null, "base": "USD", "cotada": "PYG",
      "compra": "5944.76", "venda": "5944.76", "tipo": "referencia" }
  ],
  "transferencias": [
    { "de": "BRL@brbank", "para": "PYG@ueno", "taxa": "1101", "custo_pct": "0", "custo_fixo": "0",
      "minutos": 2880, "via": "Pix → Western Union → conta ueno (tarifa 100 % desconto)", "confianca": "estimada" },
    { "de": "USD@ueno", "para": "USD@nomad", "taxa": "1", "custo_pct": "0.003", "custo_fixo": "0",
      "minutos": 1440, "via": "transferência USD (custo a confirmar)", "confianca": "incompleta" },
    { "de": "PYG@ueno", "para": "PYG@cash:CDE", "taxa": "1", "minutos": 30, "via": "saque", "confianca": "estimada" },
    { "de": "PYG@cash:CDE", "para": "PYG@chaco:CDE", "taxa": "1", "minutos": 10, "via": "balcão", "confianca": "cotada" }
  ],
  "saldos": { "BRL@brbank": "25000", "USD@nomad": "1500", "PYG@ueno": "1250000" },
  "max_arestas": 4,
  "roi_minimo": null
}
```

## Campos

| Campo | Valores |
|---|---|
| `fonte` | identificador da fonte/conta; vira o venue (`fonte` ou `fonte:cidade`) |
| `cidade` | `CDE`, `ASU`, `PJC` ou `null` (digital) |
| `base`, `cotada` | moedas; `compra`/`venda` = unidades de `cotada` por 1 `base`, na perspectiva da fonte |
| `modalidade` | `dinheiro`, `transferencia`, `conta`, `cartao_debito`, `cartao_credito`, `cartao_virtual` |
| `tipo` | `executavel`, `indicativa`, `referencia` (referência é ignorada como aresta) |
| `taxas` | lista `{rotulo, valor, moeda}`; rótulo com `%` é tratado como custo percentual sobre a entrada |
| `montante` | se a cotação vale só para um montante (simuladores), a aresta só aceita esse valor |
| `transferencias[].de/para` | nós `MOEDA@venue` |
| `confianca` | `cotada`, `estimada`, `incompleta` |
| `saldos` | montante livre por nó (só nós com saldo iniciam ciclos) |

Saída (`--json`): lista ordenada por ROI com `inicio`, `caminho`, `arestas`, `entrada`, `saida`, `ganho`,
`roi`, `roi_dia`, `minutos`, `confianca`, `canal`, `ranking_principal`, `motivo`.
