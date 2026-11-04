-- Testes da impressão digital do vigia (função pura, sem rede). Rode depois de vigia.sql:
--   psql "$DATABASE_URL" -f deploy/supabase/tests/fingerprint_check.sql
-- Sem dados de produção e sem segredos. Falha com RAISE EXCEPTION se alguma asserção quebrar.
do $check$
begin
  -- mudança de cotação muda a impressão digital (inteiros e decimais, com ponto ou vírgula)
  assert public.fx_watch_fingerprint('USD 6.085 BRL 1.110') <> public.fx_watch_fingerprint('USD 6.086 BRL 1.110'),
    'cotação com ponto deveria mudar';
  assert public.fx_watch_fingerprint('BRL 5,4935') <> public.fx_watch_fingerprint('BRL 5,4936'),
    'cotação com vírgula deveria mudar';
  assert public.fx_watch_fingerprint('6060.86') <> public.fx_watch_fingerprint('6060.87'),
    'decimal sem separador de milhar deveria mudar';
  assert public.fx_watch_fingerprint('PYG 7350') <> public.fx_watch_fingerprint('PYG 7360'),
    'inteiro de 4 dígitos (guarani) deveria mudar';

  -- horas hh:mm não contam
  assert public.fx_watch_fingerprint('atualizado 10:30 USD 6.085')
      = public.fx_watch_fingerprint('atualizado 11:45 USD 6.085'),
    'hora não deveria mudar a impressão digital';

  -- números de 1 ou 2 dígitos sem separador não contam (dia, mês, minuto)
  assert public.fx_watch_fingerprint('dia 04 mes 11 USD 6.085')
      = public.fx_watch_fingerprint('dia 05 mes 12 USD 6.085'),
    'números de 1-2 dígitos não deveriam mudar a impressão digital';

  -- 7 ou mais dígitos inteiros não contam (ids, timestamps em ms, tokens numéricos)
  assert public.fx_watch_fingerprint('id 12345678 USD 6.085')
      = public.fx_watch_fingerprint('id 87654321 USD 6.085'),
    'número de 8 dígitos (id) não deveria mudar a impressão digital';

  -- tokens aleatórios de página (CSRF, nonces) colados em letras não mudam a impressão digital
  -- (caso real medido no maxicambios: um "494" dentro de um token mudava a cada busca)
  assert public.fx_watch_fingerprint('<input value="qiwxz1hcAov494sci2nHl">')
      = public.fx_watch_fingerprint('<input value="qiwxz1hcAov495sci2nHl">'),
    'número colado em letras (token aleatório) não deveria mudar a impressão digital';

  -- limitação conhecida: inteiro colado em letra (PYG7350, sem espaço) não conta; decimal colado conta
  assert public.fx_watch_fingerprint('PYG7350') = public.fx_watch_fingerprint('PYG7360'),
    'inteiro colado em letra não é contado (limitação documentada)';
  assert public.fx_watch_fingerprint('USD6.085') <> public.fx_watch_fingerprint('USD6.086'),
    'decimal colado em letra deveria contar';

  -- texto sem números: fingerprint é sempre o mesmo (md5 de string vazia), sem erro
  assert public.fx_watch_fingerprint('sem números aqui') = public.fx_watch_fingerprint(''),
    'texto sem números deveria ter impressão digital vazia';
  assert public.fx_watch_fingerprint(null) = public.fx_watch_fingerprint(''),
    'nulo deveria tratar como vazio';

  -- a ordem dos números importa (layout trocado é mudança)
  assert public.fx_watch_fingerprint('6.085 1.110') <> public.fx_watch_fingerprint('1.110 6.085'),
    'troca de ordem deveria mudar a impressão digital';

  raise notice 'fingerprint_check: todas as asserções passaram';
end
$check$;
