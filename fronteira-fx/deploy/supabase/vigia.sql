-- Vigia de mudanças do Fronteira FX (coleta ao vivo sem servidor próprio).
--
-- O próprio Postgres do Supabase confere as fontes com pg_net (uma requisição por fonte, no máximo a cada
-- min_interval_s) e só chama a API na Vercel quando a impressão digital dos números da página mudou.
-- Ver fronteira-fx/docs/deploy.md, seção "Vigia de mudanças no Supabase".
--
-- Idempotente: pode rodar de novo. Sem segredos neste arquivo: o Bearer fica no Vault (nome fx_cron_secret).
-- Pré-requisitos (uma vez, no SQL Editor): create extension pg_net; create extension pg_cron;
-- O agendamento do passo 9 é opcional e fica comentado: rode você, depois de conferir os alvos.

-- 1. Configuração: a URL da API, sem barra no fim. Uma linha só.
create table if not exists public.fx_watch_config (
  key text primary key check (key = 'api_url'),
  value text not null check (value ~ '^https://[^/[:space:]]+$')
);

-- 2. Alvos: uma URL por fonte (a que o adaptador consulta de fato; ver docs/deploy.md).
create table if not exists public.fx_watch_targets (
  source_id text primary key,
  url text not null,
  method text not null default 'GET' check (method in ('GET', 'POST')),
  headers jsonb not null default '{}'::jsonb,
  body jsonb,
  min_interval_s int not null default 60 check (min_interval_s >= 60),
  volatile boolean not null default false,  -- preço de mercado que muda a cada minuto: API no máximo a cada 5 min
  enabled boolean not null default true,
  last_fetch_at timestamptz,
  last_fp text,
  last_change_at timestamptz,
  last_status int,
  last_called_api_at timestamptz
);

-- 3. Pedidos pendentes (pg_net): um por vez por fonte, lidos depois em net._http_response.
create table if not exists public.fx_watch_inflight (
  request_id bigint primary key,
  source_id text not null,
  created_at timestamptz not null default now()
);

-- Só o dono (postgres, que roda o cron e a função) acessa estas tabelas. RLS ligado e sem políticas.
alter table public.fx_watch_config enable row level security;
alter table public.fx_watch_targets enable row level security;
alter table public.fx_watch_inflight enable row level security;
revoke all on public.fx_watch_config, public.fx_watch_targets, public.fx_watch_inflight from anon, authenticated;

-- 4. Impressão digital: md5 dos números da página, na ordem em que aparecem.
-- Pega cotações com separador (6.085, 1.110, 5,4935, 6060.86) e inteiros de 3 a 6 dígitos (7350, guaranis).
-- Ignora: números com 7+ dígitos inteiros; horas (hh:mm); números de 1 ou 2 dígitos (dias, meses, minutos).
-- Inteiros só contam quando não colam em letras: tokens aleatórios de páginas (CSRF, nonces: "x7a494b") mudam
-- a cada busca e gerariam chamadas à API o tempo todo. Função pura, testável sozinha.
create or replace function public.fx_watch_fingerprint(p_body text)
returns text
language sql
immutable
set search_path = pg_catalog
as $fp$
  select md5(coalesce(string_agg(coalesce(r.m[1], r.m[2]), ' ' order by r.ord), ''))
  from regexp_matches(
         coalesce(p_body, ''),
         '(?:(?<![0-9.,])([0-9]{1,6}[.,][0-9]{1,6})(?![0-9])|(?<![0-9A-Za-z.,])([0-9]{3,6})(?![0-9A-Za-z]))',
         'g'
       ) with ordinality as r(m, ord)
$fp$;

-- 5. A rodada, a cada 30 s (pelo pg_cron). Em ordem:
--    (1) lê as respostas prontas dos pedidos em fx_watch_inflight; 2xx com impressão digital nova marca a fonte
--        como mudada; pedidos sem resposta há mais de 2 min saem;
--    (2) chama a API UMA vez com as fontes que mudaram e ainda não foram enviadas (volátil: no máximo a cada 5 min);
--    (3) dispara as requisições vencidas (min_interval_s), uma por fonte.
--    Devolve um resumo em jsonb (sem segredo, sem corpo de resposta).
create or replace function public.fx_watch_tick()
returns jsonb
language plpgsql
security definer
set search_path = pg_catalog, pg_temp
as $tick$
declare
  -- user-agent do projeto: o mesmo USER_AGENT de backend/src/fronteira_fx/adapters/_http.py (há um teste que compara)
  v_ua constant text := 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36';
  v_now timestamptz := now();
  v_api text;
  v_secret text;
  v_ids text[];
  v_called boolean := false;
  v_changed text[] := '{}';
  v_dispatched text[] := '{}';
  v_responses int := 0;
  v_fp text;
  v_req bigint;
  r record;
begin
  -- uma execução por vez (o cron pode sobrepor se a anterior demorar)
  if not pg_try_advisory_xact_lock(hashtext('fx_watch_tick')) then
    return jsonb_build_object('pulado', 'outra execução em curso');
  end if;

  -- (1) respostas prontas
  for r in
    select i.request_id, i.source_id, i.created_at, n.id as resp_id, n.status_code, n.content, n.timed_out
    from public.fx_watch_inflight i
    left join net._http_response n on n.id = i.request_id
  loop
    if r.resp_id is null then
      if r.created_at < v_now - interval '2 minutes' then
        delete from public.fx_watch_inflight where request_id = r.request_id;
      end if;
      continue;
    end if;

    v_responses := v_responses + 1;
    update public.fx_watch_targets set last_status = r.status_code where source_id = r.source_id;
    if r.status_code between 200 and 299 and not coalesce(r.timed_out, false) then
      v_fp := public.fx_watch_fingerprint(r.content);
      update public.fx_watch_targets t
         set last_fp = v_fp, last_change_at = v_now
       where t.source_id = r.source_id
         and t.last_fp is distinct from v_fp;  -- a primeira leitura conta como mudança: a API recebe o estado inicial
      if found then
        v_changed := v_changed || r.source_id;
      end if;
    end if;
    delete from public.fx_watch_inflight where request_id = r.request_id;
  end loop;

  -- (2) fontes mudadas e ainda não enviadas à API; volátil só se a última chamada tem mais de 5 min
  select array_agg(t.source_id order by t.source_id) into v_ids
  from public.fx_watch_targets t
  where t.enabled
    and t.last_change_at is not null
    and (t.last_called_api_at is null or t.last_change_at > t.last_called_api_at)
    and (not t.volatile or t.last_called_api_at is null or t.last_called_api_at < v_now - interval '5 minutes');

  select c.value into v_api from public.fx_watch_config c where c.key = 'api_url';
  select s.decrypted_secret into v_secret from vault.decrypted_secrets s where s.name = 'fx_cron_secret';

  if v_ids is not null and v_api is not null and v_secret is not null then
    perform net.http_post(
      url := v_api || '/v1/internal/collect',
      body := jsonb_build_object('sources', to_jsonb(v_ids)),
      headers := jsonb_build_object(
        'Content-Type', 'application/json',
        'User-Agent', v_ua,
        'Authorization', 'Bearer ' || v_secret
      ),
      timeout_milliseconds := 55000
    );
    update public.fx_watch_targets set last_called_api_at = v_now where source_id = any(v_ids);
    v_called := true;
  end if;

  -- (3) requisições vencidas; uma por fonte e nunca duas ao mesmo tempo para a mesma fonte
  for r in
    select t.source_id, t.url, t.method, t.headers, t.body
    from public.fx_watch_targets t
    where t.enabled
      and (t.last_fetch_at is null or t.last_fetch_at + make_interval(secs => t.min_interval_s) <= v_now)
      and not exists (select 1 from public.fx_watch_inflight i where i.source_id = t.source_id)
    order by t.source_id
  loop
    if r.method = 'POST' then
      v_req := net.http_post(
        url := r.url,
        body := coalesce(r.body, '{}'::jsonb),
        headers := jsonb_build_object('User-Agent', v_ua, 'Content-Type', 'application/json') || coalesce(r.headers, '{}'::jsonb),
        timeout_milliseconds := 20000
      );
    else
      v_req := net.http_get(
        url := r.url,
        headers := jsonb_build_object('User-Agent', v_ua) || coalesce(r.headers, '{}'::jsonb),
        timeout_milliseconds := 20000
      );
    end if;
    insert into public.fx_watch_inflight (request_id, source_id, created_at) values (v_req, r.source_id, v_now);
    update public.fx_watch_targets set last_fetch_at = v_now where source_id = r.source_id;
    v_dispatched := v_dispatched || r.source_id;
  end loop;

  return jsonb_build_object(
    'respostas', v_responses,
    'mudaram', to_jsonb(v_changed),
    'api_chamada', v_called,
    'api_fontes', coalesce(to_jsonb(v_ids), '[]'::jsonb),
    'api_configurada', v_api is not null and v_secret is not null,
    'disparadas', to_jsonb(v_dispatched)
  );
end;
$tick$;

revoke all on function public.fx_watch_tick() from public;
revoke all on function public.fx_watch_fingerprint(text) from public;

-- 6. Alvos (seed). Um por fonte do registro, exceto westernunion (precisa de navegador). Idempotente: atualiza
-- URL, cabeçalhos e intervalo, sem mexer no estado de execução (last_*).
-- Cabeçalhos: os mesmos do fetch padrão de cada adaptador (default_headers em _http.py). O user-agent vem da função.
insert into public.fx_watch_targets (source_id, url, method, headers, min_interval_s, volatile) values
  -- Alberdi: JSON do tablero (ws/getTablero.json.php), filiais ASU e CDE
  ('alberdi', 'https://www.cambiosalberdi.com/ws/getTablero.json.php', 'GET',
   '{"Accept": "application/json, text/plain, */*", "Accept-Language": "es-PY,es;q=0.9,pt-BR;q=0.8,en;q=0.7", "Referer": "https://www.cambiosalberdi.com/"}',
   60, false),
  -- Bonanza: JSON do tablero (api/board), filiais CDE e ASU
  ('bonanza', 'https://www.bonanzacambios.com.py/api/board', 'GET',
   '{"Accept": "application/json, text/plain, */*", "Accept-Language": "es-PY,es;q=0.9,pt-BR;q=0.8,en;q=0.7", "Referer": "https://www.bonanzacambios.com.py/"}',
   60, false),
  -- BCP: referencial (sem compra/venta), publicado em dias úteis. Feed Frankfurter, o mesmo do primeiro passo do adaptador
  -- (o adaptador consulta USD e BRL; aqui só USD). Intervalo de 5 min, não 60 s: é referência diária.
  ('bcp', 'https://api.frankfurter.dev/v2/providers/bcp/rates?base=USD&quotes=PYG', 'GET',
   '{"Accept": "application/json, text/plain, */*", "Accept-Language": "es-PY,es;q=0.9,pt-BR;q=0.8,en;q=0.7"}',
   300, false),
  -- Chaco: API por filial. Uma filial só (remote code 1, Casa Central ASU): ver a limitação em docs/deploy.md
  ('chaco', 'https://www.cambioschaco.com.py/api/branch_office/1/exchange', 'GET',
   '{"Accept": "application/json, text/plain, */*", "Accept-Language": "es-PY,es;q=0.9,pt-BR;q=0.8,en;q=0.7", "Referer": "https://www.cambioschaco.com.py/"}',
   60, false),
  -- Dólar PY (agregador de mercado): preço de mercado, volátil
  ('dolarpy', 'https://dolar.melizeche.com/api/1.0/', 'GET',
   '{"Accept": "application/json, text/plain, */*", "Accept-Language": "es-PY,es;q=0.9,pt-BR;q=0.8,en;q=0.7"}',
   60, true),
  -- Maxi Cambios: HTML da home (tabela de cotações, ASU)
  ('maxicambios', 'https://www.maxicambios.com.py/', 'GET',
   '{"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", "Accept-Language": "es-PY,es;q=0.9,pt-BR;q=0.8,en;q=0.7"}',
   60, false),
  -- MyD: HTML da home (banners de cotação, CDE/ASU/PJC)
  ('myd', 'https://www.mydcambios.com.py/', 'GET',
   '{"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", "Accept-Language": "es-PY,es;q=0.9,pt-BR;q=0.8,en;q=0.7"}',
   60, false),
  -- Nomad: JSON da API de câmbio (a página é renderizada no cliente). Preço de mercado, volátil
  ('nomad', 'https://api.benomad.us/forex-rates-s3/v1/exchanges:90-days', 'GET',
   '{"Accept": "application/json, text/plain, */*", "Accept-Language": "es-PY,es;q=0.9,pt-BR;q=0.8,en;q=0.7", "Origin": "https://www.nomadglobal.com", "Referer": "https://www.nomadglobal.com/cotacao/dolar-hoje"}',
   60, true),
  -- Norte: HTML da home (filial padrão). As outras filiais exigem POST do Livewire: ver docs/deploy.md
  ('norte', 'https://www.nortecambios.com.py/', 'GET',
   '{"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", "Accept-Language": "es-PY,es;q=0.9,pt-BR;q=0.8,en;q=0.7"}',
   60, false),
  -- Revolut: cotação USD->BRL do endpoint JSON, com os parâmetros padrão do fetch (1000 USD, Brasil, pt-BR).
  -- Revolut bloqueia clientes que não são navegador: o alvo pode voltar 403 (fica em last_status). Volátil.
  ('revolut', 'https://www.revolut.com/api/exchange/quote?amount=1000&country=BR&fromCurrency=USD&isRecipientAmount=false&toCurrency=BRL&localeCode=pt-BR', 'GET',
   '{"Accept": "application/json, text/plain, */*", "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8", "Referer": "https://www.revolut.com/currency-converter/"}',
   60, true)
on conflict (source_id) do update set
  url = excluded.url,
  method = excluded.method,
  headers = excluded.headers,
  body = excluded.body,
  min_interval_s = excluded.min_interval_s,
  volatile = excluded.volatile;

-- 7. A URL da API (passo manual, com o domínio da função Vercel; sem barra no fim). Sem linha, a rodada não chama a API.
-- insert into public.fx_watch_config (key, value) values ('api_url', 'https://<API_VERCEL>')
--   on conflict (key) do update set value = excluded.value;

-- 8. O segredo fica no Vault, não aqui (mesmo nome usado em docs/deploy.md):
-- select vault.create_secret('<CRON_SECRET>', 'fx_cron_secret', 'Bearer de /v1/internal/collect');

-- 9. Agendamento (passo opcional; rode você): a cada 30 s. Com o piso de 60 s por fonte, cada fonte é consultada
-- a cada 60 a 90 s.
-- select cron.schedule('fx-vigia', '30 seconds', 'select public.fx_watch_tick()');
-- Para parar: select cron.unschedule('fx-vigia');
