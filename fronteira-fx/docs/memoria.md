# Memória do agente

A memória é o caderno do terminal. Ela guarda coisas que valem a pena lembrar entre uma conversa e outra:
o que você decidiu, como você prefere operar, o que aprendemos sobre um provedor e como deu uma operação
que já foi feita. Assim o agente não precisa perguntar de novo, nem repetir um erro que já custou dinheiro.

Código: `backend/src/fronteira_fx/memory/`. Contrato da API: seção "Memória do agente" em `docs/api-contract.md`.

## Para que serve

Exemplos reais do dia a dia:

- **Limite de segurança:** "não usar Nomad acima de US$ 1.000 sem confirmar IOF". Quando o agente for
  sugerir uma rota pela Nomad com valor alto, ele lembra da regra antes de recomendar.
- **Regra de decisão:** "Alberdi PJC melhora acima de R$ 25 mil". Serve para comparar rotas com o mesmo
  capital sem refazer a conta toda vez.
- **Preferência:** "prefiro receber em ueno, não em Revolut". O agente aplica sem você repetir.
- **Fato sobre um provedor:** "ueno cobra IOF no cartão de crédito, não no débito". Informação estável que
  muda a conta.
- **Resultado de operação:** "remessa Western Union CDE → ueno levou 2 dias úteis em março". Dá base
  para estimar prazo da próxima.

## Os quatro tipos

| Tipo (`kind`) | O que guarda | Exemplo |
|---|---|---|
| `preference` | Como você quer operar | "prefere Pix para receber" |
| `decision` | Regra ou escolha que você tomou | "não usar Nomad acima de US$ 1.000 sem confirmar IOF" |
| `fact` | Informação sobre provedor, taxa ou prazo | "ueno cobra IOF no cartão de crédito" |
| `outcome` | Resultado de uma operação já feita | "remessa WU CDE → ueno levou 2 dias" |

Cada memória também tem:

- **`tags`**: marcadores curtos para achar depois, como `ueno`, `nomad`, `iof`. São gravadas em minúsculas e
  sem repetição. Até 20 por memória, 40 caracteres cada.
- **`source`**: quem gravou, `user` (você) ou `agent` (o agente, ao registrar algo que aprendeu).
- **`expires_at`**: data de validade, opcional. Use para coisas que mudam, como uma promoção ou uma taxa
  temporária (`ttl_days` de 1 a 3650).

Texto: até 2000 caracteres. Escreva curto e completo, com o valor e a condição. "Nomad: cuidado com IOF
acima de 1000" é pior que "não usar Nomad acima de US$ 1.000 sem confirmar IOF".

## Como o agente usa

O agente acessa a memória pelo MCP do terminal, com quatro ferramentas. Os argumentos são os mesmos da API.

**`remember`**: grava uma memória.

```json
{
  "kind": "decision",
  "text": "não usar Nomad acima de US$ 1.000 sem confirmar IOF",
  "tags": ["nomad", "iof"],
  "ttl_days": 365
}
```

**`recall`**: busca. `q` procura palavras no texto e nas tags, sem diferenciar maiúsculas nem acentos
("cartão" acha "cartao"). Quando há mais de um resultado, os que têm mais palavras batendo vêm primeiro;
empates saem do mais recente. Sem `q`, devolve as mais recentes. Também aceita `kind`, `tag` e `limit`
(1 a 100, padrão 20).

```json
{ "q": "ueno cartão", "limit": 5 }
```

**`memory_summary`**: devolve um bloco curto em português, pronto para entrar no contexto do agente. Ele
mostra as memórias ativas de cada tipo, com as mais recentes primeiro:

```
Preferências: prefere Pix para receber
Decisões: não usar Nomad acima de US$ 1.000 sem confirmar IOF; Alberdi PJC melhora acima de R$ 25 mil
Fatos: ueno cobra IOF no cartão de crédito
Resultados: remessa WU CDE → ueno levou 2 dias úteis
```

Sem memórias ativas, o bloco vem vazio.

**`forget`**: apaga uma memória pelo `id`. Use quando a regra mudou ou você não quer mais que o agente a
considere. Se o `id` não existir (ou a memória já tiver expirado), a resposta é "não encontrada".

Quando o agente grava algo sozinho, ele deve usar `source` `agent`. Assim, no futuro, dá para ver o que foi
decidido por você e o que foi sugerido por ele.

## Expiração

Memória com `ttl_days` some das buscas e do resumo assim que vence. Ela continua no banco até a limpeza
(`purge_expired`), que apaga de vez as vencidas. Memórias sem validade ficam até você apagar.

## Privacidade

- **Onde fica:** a memória é gravada no banco do próprio backend (SQLite no desenvolvimento, PostgreSQL no
  `docker-compose`). Não há serviço externo, nem busca vetorial, nem envio para terceiros pelo módulo.
- **O que o agente recebe:** quando o agente lê uma memória (`recall` ou `memory_summary`), o texto vai para
  o contexto dele, e o modelo de IA que ele usa recebe esse texto como parte da conversa. Por isso, o que
  você não quer que apareça numa conversa com o agente não deve ir para a memória.
- **Não grave segredos:** senha, PIN, chave de API, token, número completo de cartão ou de conta. Use
  "conta ueno USD" em vez do número.
- **Você controla:** o que foi gravado pode ser listado (`recall`) e apagado (`forget`).

## Como o core do backend monta o módulo

O módulo não sobe sozinho. O core (`main.py` e o Alembic) faz três ligações:

1. **Rotas e autenticação.** Incluir o router com a mesma proteção das escritas (`ApiKey`):

   ```python
   from fronteira_fx.memory.router import router as memory_router

   app.include_router(memory_router, dependencies=[ApiKey])
   ```

2. **Serviço com banco real.** Sem essa sobrescrita, o módulo usa armazenamento em memória, que some ao
   reiniciar:

   ```python
   from fronteira_fx.memory.router import get_service
   from fronteira_fx.memory.service import MemoryService
   from fronteira_fx.memory.store import SqlStore, create_memory_tables

   memory_service = MemoryService(SqlStore(app.state.session_factory))
   app.dependency_overrides[get_service] = lambda: memory_service
   ```

   Em dev com `AUTO_CREATE_SCHEMA=true`, chame também `create_memory_tables(app.state.engine)` no boot.

3. **Tabela no Alembic.** A tabela `agent_memories` tem base própria (`MemoryBase`), separada de `models.Base`.
   No `alembic/env.py`, passe as duas bases ao autogenerate:

   ```python
   from fronteira_fx.memory.store import MemoryBase

   target_metadata = [Base.metadata, MemoryBase.metadata]
   ```

   Depois gere a migração (`uv run alembic revision --autogenerate -m "memoria do agente"`) e revise antes de
   aplicar.

4. **Ferramentas MCP.** Incluir `remember`, `recall`, `forget` e `memory_summary` na lista de operações
   expostas ao MCP. As chamadas do agente devem enviar o header `X-Memory-Source: agent`, para que a origem
   fique registrada. Sem o header, a memória fica como `user`.

Limpeza periódica das vencidas: `MemoryService.purge_expired()` pode rodar no worker. Não é obrigatório,
porque as vencidas já ficam ocultas.

## Limites e garantias

- Texto: 1 a 2000 caracteres. Tags: até 20, 1 a 40 caracteres cada.
- Validade: 1 a 3650 dias, ou sem validade.
- Busca: 1 a 100 resultados por chamada.
- Resumo: até 5 itens por tipo por padrão; cada item é encurtado para 200 caracteres.
- Os dados ficam no banco do backend. O módulo não usa armazenamento do navegador nem envia dados para outro serviço.
