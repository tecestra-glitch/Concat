# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

O dono do terminal, que usa para uso pessoal. Ele não é designer e sabe o que quer ver: quanto cada casa paga pelo
dólar e pelo real no Paraguai, onde converter com menos custo e o que vale a pena agora. A situação é de quem
move dinheiro entre Brasil e Paraguai com frequência e compara várias casas de câmbio e bancos.
*Inferido do briefing e do CLAUDE.md; confirmar se houver outros usuários.*

## Product Purpose

Terminal pessoal de câmbio BRL · USD · PYG, com cotações das casas em CDE, ASU e PJC, remessas, cartões e um ranking
de oportunidades que mostra ganho líquido e ROI com todos os custos. O sucesso é o dono abrir a tela inicial e
entender em segundos onde está o melhor câmbio, com quanto de confiança, sem precisar procurar nada.

## Positioning

Honestidade de dados como produto: cada número diz de onde veio (real, simulação ou demonstração), se o custo está
completo, e nunca vira "lucro confirmado" quando falta um custo. Não é corretora nem executa nada; é leitura.

## Operating Context

- Uso diário no computador e no celular, em visitas curtas para checar cotações e oportunidades.
- Pregão: panorama das cotações publicadas pelas casas, com livro, velas e fita. Não é bolsa.
- Fontes sem API são sondadas com cuidado (mín. 60 s por fonte), com recuo após erro.

## Capabilities and Constraints

- Três modos de dados que nunca se misturam: real, simulação e demonstração (faixa visível em toda tela).
- Moedas do contrato: BRL, USD e PYG. ARS, EUR e USDT aparecem só como bandeira ou ícone da interface.
- Cidades de cobertura: CDE, ASU e PJC, todas no Paraguai. Não há campo de país no contrato ainda (fase 2).
- Nada executa movimentação financeira; conexão de contas e execução são fases posteriores.
- Um banco paraguaio fechou em 03/11/2026 (resolução do BCP) e saiu do frontend; o backend sai na integração final.
- Bancos novos (Basa, Familiar, GNB e outros) entram como fontes quando o backend os devolver; a UI já os acomoda.

## Brand Commitments

- Nome: Fronteira FX. Tema escuro é o padrão; o claro existe.
- Um acento só (azul). Verde e vermelho sempre com sinal e texto.
- Sem números animados: nada se move sobre um valor que muda; só um realce curto.

## Evidence on Hand

- Dados de demonstração em `src/lib/api/demo-data.ts` e `src/lib/pregao/demo.ts` (ilustrativos, marcados como demo).
- Capturas de antes da reforma em `dev/ui/audit/` (1440 e 390). Nenhuma métrica de uso real existe ainda.

## Product Principles

1. O número é o protagonista: tabular, alinhado, sem quebra de linha e sem animação sobre o valor.
2. Modo e confiança aparecem onde a decisão acontece, não escondidos em tooltip.
3. Custo desconhecido é "não confirmado", nunca lucro.
4. Uma tela, uma pergunta: a home responde "onde está o melhor câmbio agora".

## Accessibility & Inclusion

WCAG 2.2 AA em contraste e foco visível; alvos de toque de 44 px no celular; `prefers-reduced-motion` respeitado
(nenhuma animação se repete nem pisca); textos com 12 px ou mais; tudo utilizável pelo teclado.
