# Mini navegador (Fronteira FX)

Função Vercel que roda o fluxo da Western Union (BR → PY) num Chromium sem tela e devolve o `scenario` que o
adaptador Python (`backend/src/fronteira_fx/adapters/westernunion.py`) já sabe ler. Projeto separado do Next.js
de `fronteira-fx/`, com workspace próprio.

## O que faz

- `POST /api/westernunion` com `Authorization: Bearer <BROWSER_SECRET>` (comparação em tempo constante).
- Corpo JSON (validado): `amount_brl` (decimal, 1 a 100000), `payment` (`pix` | `bank_transfer` | `card`),
  `receive` (`bank_account` | `cash_pickup`), `bank` opcional, `screenshot` opcional.
- A URL é fixa (a página inicial da Western Union). O cliente nunca envia URL.
- Resposta: `status` (`ok` | `degraded` | `blocked` | `error`), `message`, `trail`, `scenario` e, com
  `screenshot: true`, `screenshot_png_b64`. Sem cookies, cabeçalhos ou sessão.
- Sem `BROWSER_SECRET` configurado a rota responde 404. Segredo errado ou ausente: 401.

Não movimenta dinheiro, não contorna anti-bot e não usa modo furtivo. Se a página bloquear, responde `blocked`.

## Testar localmente

```bash
pnpm install --frozen-lockfile
pnpm typecheck && pnpm lint && pnpm test    # sem rede
# visita real (uma vez; consome CPU e toca o site público):
CHROMIUM_EXECUTABLE_PATH=/caminho/do/chrome-headless-shell pnpm smoke
```

`CHROMIUM_EXECUTABLE_PATH` escolhe o binário local. Sem essa variável, a função usa o Chromium que
`@sparticuz/chromium` descompacta em `/tmp` (produção). `SMOKE_OUT_DIR=<pasta>` salva a captura do smoke.

## Variáveis

| Variável | Onde | Uso |
|---|---|---|
| `BROWSER_SECRET` | Vercel (Sensitive) | Bearer aceito pela função. Mesmo valor de `FX_BROWSER_SECRET` no backend. |
| `CHROMIUM_EXECUTABLE_PATH` | local | Binário Chromium para testes e smoke. Não defina na Vercel. |

Nunca grave o segredo em arquivo, teste ou log.

## Versões

- `playwright-core` 1.63.0 e `@sparticuz/chromium` 153.0.0: o Chromium do pacote (153.0.8010.12) é o mesmo que
  o `playwright-core` 1.63.0 espera.
- Todas as versões fixas foram publicadas há pelo menos 14 dias.

## Custos e limites

- Cada execução gasta alguns segundos de CPU e memória (2048 MB). No plano grátis da Vercel há cerca de 4 horas
  de CPU por mês: consulte a Western Union **no máximo a cada 2 horas**. O backend aplica esse intervalo
  (`REMOTE_BROWSER_MIN_INTERVAL_S`, padrão 7200).
- `maxDuration` 120 s. O fluxo tem orçamento de 110 s e responde `degraded` ao estourar.
- Região `gru1` (São Paulo).

## Deploy

Pelo Vercel com Root Directory `fronteira-fx/browser`. Como o `packageManager` fixa o pnpm, use
`ENABLE_EXPERIMENTAL_COREPACK=1` (igual ao projeto principal). Não há deploy automático neste repositório.
