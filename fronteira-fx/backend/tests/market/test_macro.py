"""Fontes macro (FRED DTWEXBGS, BCB SGS 11/432/433, brapi só para teste): sem rede, transporte mock (respx).

Critérios: 429 com backoff; SGS sempre com dataInicial e dataFinal e janela de até 10 anos; chave só por variável
de ambiente; limite de FRED abaixo de 120 req/min; yfinance fora de produção.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx
import pytest
import respx
from pydantic import SecretStr

from fronteira_fx.config import Settings
from fronteira_fx.market import brapi, macro
from fronteira_fx.market import quotes as q
from fronteira_fx.market.service import MarketPoller, build_scheduler
from fronteira_fx.market.throttle import BlockedError, SlidingWindowLimiter, backoff_delay, parse_retry_after

from .conftest import market_settings, read_fixture
from .test_poller import Clock, make_poller

MARKET_DIR = Path(__file__).resolve().parents[2] / "src" / "fronteira_fx" / "market"
SRC_DIR = Path(__file__).resolve().parents[2] / "src" / "fronteira_fx"
FAKE_KEY = "fake-key-sanitizada-0123"  # chave falsa de teste; não é segredo


class Recorder:
    """Substitui `asyncio.sleep` nos testes: registra as esperas sem dormir de verdade."""

    def __init__(self) -> None:
        self.waits: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.waits.append(seconds)


# ------------------------------------------------------------------ SGS: janela obrigatória
def test_sgs_request_always_sends_both_dates_in_dd_mm_yyyy():
    url, params = q.sgs_request(11, date(2026, 10, 1), date(2026, 11, 4))
    assert url == "https://api.bcb.gov.br/dados/serie/bcdata.sgs.11/dados"
    assert params == {"formato": "json", "dataInicial": "01/10/2026", "dataFinal": "04/11/2026"}
    assert "ultimos" not in url


def test_sgs_window_of_exactly_ten_years_is_accepted_and_one_day_more_is_refused():
    start = date(2016, 11, 4)
    q.sgs_request(432, start, date(2026, 11, 4))  # exatamente 10 anos
    with pytest.raises(ValueError, match="10 anos"):
        q.sgs_request(432, start, date(2026, 11, 5))


def test_sgs_window_starting_on_leap_day_and_inverted_window():
    q.sgs_request(11, date(2024, 2, 29), date(2034, 2, 28))  # 10 anos a partir de 29/02 cai em 28/02
    with pytest.raises(ValueError, match="10 anos"):
        q.sgs_request(11, date(2024, 2, 29), date(2034, 3, 1))
    with pytest.raises(ValueError, match="posterior"):
        q.sgs_request(11, date(2026, 11, 4), date(2026, 11, 3))


def test_every_configured_sgs_series_has_a_lookback_and_a_bounded_window():
    codes = {code for code, _i, _l in q.BCB_SERIES}
    assert {1, 10813, 11, 432, 433} <= codes
    assert codes <= set(q.SGS_LOOKBACK_DAYS)
    today = date(2026, 11, 4)
    for code in codes:
        start = today - timedelta(days=q.SGS_LOOKBACK_DAYS[code])
        _url, params = q.sgs_request(code, start, today)
        assert params["dataInicial"] and params["dataFinal"]
        assert (today - start).days <= 10 * 366


@respx.mock
async def test_poller_never_calls_sgs_without_dates_and_never_over_ten_years(market_factory, monkeypatch):
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    seen: list[httpx.URL] = []

    def responder(request: httpx.Request) -> httpx.Response:
        seen.append(request.url)
        code = request.url.path.split("sgs.")[1].split("/")[0]
        name = {
            "1": "bcb_sgs_1_ultimos2.json",
            "10813": "bcb_sgs_10813_ultimos2.json",
            "11": "bcb_sgs_11_janela.json",
            "432": "bcb_sgs_432_ultimo.json",
            "433": "bcb_sgs_433_janela.json",
        }[code]
        return httpx.Response(200, content=read_fixture(name))

    respx.route(url__startswith="https://api.bcb.gov.br/").mock(side_effect=responder)
    poller = make_poller(market_factory, Clock(datetime(2026, 11, 4, 12, tzinfo=UTC)), keep={"bcb-sgs"})
    try:
        results = await poller.run_once()
    finally:
        await poller.aclose()
    assert results[0].ok is True
    assert len(seen) == len(q.BCB_SERIES)
    for url in seen:
        assert "ultimos" not in url.path
        start = datetime.strptime(url.params["dataInicial"], "%d/%m/%Y").date()
        end = datetime.strptime(url.params["dataFinal"], "%d/%m/%Y").date()
        assert start <= end and end <= start.replace(year=start.year + 10)


# ------------------------------------------------------------------ FRED: throttle e 429
def test_fred_limit_stays_below_published_120_per_minute():
    assert macro.FRED_MAX_PER_MINUTE < macro.FRED_LIMIT_PER_MIN == 120


def test_limiter_never_lets_more_than_the_cap_start_in_any_minute():
    limiter = SlidingWindowLimiter(macro.FRED_MAX_PER_MINUTE)
    now = 0.0
    starts: list[float] = []
    for _ in range(450):
        now += limiter.reserve(now)  # quem chama espera o tempo devolvido
        starts.append(now)
    for i, t in enumerate(starts):
        in_window = [s for s in starts if t - 60 < s <= t]
        assert len(in_window) <= macro.FRED_MAX_PER_MINUTE, (i, len(in_window))


def test_backoff_doubles_is_capped_and_honours_numeric_retry_after():
    assert [backoff_delay(n) for n in range(4)] == [2.0, 4.0, 8.0, 16.0]
    assert backoff_delay(10) == 30.0  # teto
    assert backoff_delay(0, retry_after=12.0) == 12.0
    assert backoff_delay(0, retry_after=999.0) == 30.0
    assert parse_retry_after("7") == 7.0
    assert parse_retry_after("Wed, 21 Oct 2026 07:28:00 GMT") is None
    assert parse_retry_after("-3") is None


@respx.mock
async def test_fred_429_is_retried_with_backoff_and_then_parsed():
    route = respx.get(macro.FRED_URL).mock(
        side_effect=[
            httpx.Response(429),
            httpx.Response(429, headers={"Retry-After": "1"}),
            httpx.Response(200, content=read_fixture("fred_dtwexbgs.json")),
        ]
    )
    sleeps = Recorder()
    async with httpx.AsyncClient() as client:
        data = await macro.fred_observations(
            client,
            FAKE_KEY,
            today=date(2026, 11, 4),
            limiter=SlidingWindowLimiter(macro.FRED_MAX_PER_MINUTE),
            clock=lambda: 0.0,
            sleep=sleeps,
        )
    assert route.call_count == 3
    assert sleeps.waits == [2.0, 4.0]  # 1º recuo 2 s; 2º recuo 4 s (Retry-After de 1 s não reduz o cálculo)
    draft = macro.parse_fred_observations(data)
    assert draft.price == q.Decimal("121.6656") and draft.kind == "fx_reference" and draft.source == "fred"


@respx.mock
async def test_fred_persistent_429_becomes_blocked_without_leaking_the_key():
    respx.get(macro.FRED_URL).mock(return_value=httpx.Response(429))
    sleeps = Recorder()
    async with httpx.AsyncClient() as client:
        with pytest.raises(BlockedError) as info:
            await macro.fred_observations(
                client,
                FAKE_KEY,
                today=date(2026, 11, 4),
                limiter=SlidingWindowLimiter(macro.FRED_MAX_PER_MINUTE),
                clock=lambda: 0.0,
                sleep=sleeps,
            )
    assert len(sleeps.waits) == macro.FRED_MAX_ATTEMPTS - 1
    assert FAKE_KEY not in str(info.value) and "api_key" not in str(info.value)


@respx.mock
async def test_fred_network_error_message_has_no_url_or_key():
    respx.get(macro.FRED_URL).mock(side_effect=httpx.ConnectError(f"falhou api_key={FAKE_KEY}"))
    async with httpx.AsyncClient() as client:
        with pytest.raises(macro.FredError) as info:
            await macro.fred_observations(
                client,
                FAKE_KEY,
                today=date(2026, 11, 4),
                limiter=SlidingWindowLimiter(macro.FRED_MAX_PER_MINUTE),
                clock=lambda: 0.0,
                sleep=Recorder(),
            )
    assert FAKE_KEY not in str(info.value)


def test_fred_parse_skips_missing_values_and_computes_change():
    data = {
        "observations": [
            {"date": "2026-10-27", "value": "120.0000"},
            {"date": "2026-10-28", "value": "121.2000"},
            {"date": "2026-10-29", "value": "."},
            {"date": "2026-10-30", "value": "121.6656"},
        ]
    }
    draft = macro.parse_fred_observations(data)
    assert draft.price == q.Decimal("121.6656")
    assert draft.change_pct is not None and draft.change_pct.quantize(q.Decimal("0.01")) == q.Decimal("0.38")
    assert draft.instrument.startswith("USD amplo") and "não é o DXY" in draft.label
    with pytest.raises(q.FeedFormatError):
        macro.parse_fred_observations({"observations": [{"date": "2026-10-29", "value": "."}]})


def test_fred_params_carry_the_key_only_as_a_parameter():
    params = macro.fred_params(FAKE_KEY, today=date(2026, 11, 4))
    assert params["api_key"] == FAKE_KEY and params["series_id"] == "DTWEXBGS"
    with pytest.raises(ValueError):
        macro.fred_params("", today=date(2026, 11, 4))


# ------------------------------------------------------------------ chave só por variável de ambiente
def test_fred_source_is_off_without_key_and_on_with_env_key(monkeypatch):
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    assert Settings(_env_file=None).fred_api_key is None
    assert macro.FRED_SOURCE not in {s.source_id for s in build_scheduler().sources()}

    monkeypatch.setenv("FRED_API_KEY", FAKE_KEY)
    settings = Settings(_env_file=None)
    assert settings.fred_api_key is not None and settings.fred_api_key.get_secret_value() == FAKE_KEY
    assert macro.FRED_SOURCE not in {s.source_id for s in build_scheduler().sources()}  # só com fred_enabled
    assert macro.FRED_SOURCE in {s.source_id for s in build_scheduler(fred_enabled=True).sources()}


def test_secret_is_not_shown_by_repr_of_settings(monkeypatch):
    monkeypatch.setenv("FRED_API_KEY", FAKE_KEY)
    monkeypatch.setenv("BRAPI_TOKEN", "tok-sanitizado")
    settings = Settings(_env_file=None)
    text = repr(settings)
    assert FAKE_KEY not in text and "tok-sanitizado" not in text


@respx.mock
async def test_poller_without_key_never_touches_fred(market_factory, monkeypatch):
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    route = respx.get(macro.FRED_URL).mock(return_value=httpx.Response(200, json={"observations": []}))
    poller = make_poller(market_factory, Clock(datetime(2026, 11, 4, 12, tzinfo=UTC)), keep={macro.FRED_SOURCE})
    try:
        assert await poller.run_once() == []  # fonte nem registrada
        assert await poller._poll_fred(datetime(2026, 11, 4, 12, tzinfo=UTC)) is False
    finally:
        await poller.aclose()
    assert route.call_count == 0


@respx.mock
async def test_poller_with_env_key_polls_fred_once_and_stores_a_reference(market_factory, monkeypatch):
    monkeypatch.setenv("FRED_API_KEY", FAKE_KEY)
    route = respx.get(macro.FRED_URL).mock(return_value=httpx.Response(200, content=read_fixture("fred_dtwexbgs.json")))
    settings = market_settings("real")
    settings = settings.model_copy(update={"fred_api_key": SecretStr(FAKE_KEY)})
    clock = Clock(datetime(2026, 11, 4, 12, tzinfo=UTC))
    poller = MarketPoller(market_factory, settings, clock=clock)
    for source in poller.scheduler.sources():
        if source.source_id != macro.FRED_SOURCE:
            poller.scheduler.remove_source(source.source_id)
    try:
        results = await poller.run_once()
    finally:
        await poller.aclose()
    assert results[0].ok is True and route.call_count == 1
    assert route.calls.last.request.url.params["api_key"] == FAKE_KEY  # chave só na query, nunca em erro
    with market_factory() as s:
        from sqlalchemy import select

        from fronteira_fx.models import MarketQuote

        row = s.scalar(select(MarketQuote).where(MarketQuote.instrument == macro.FRED_INSTRUMENT))
        assert row is not None and row.source == "fred" and row.kind == "fx_reference"


# ------------------------------------------------------------------ código sem segredo e sem yfinance
def test_no_secret_literal_in_market_or_config_code():
    files = [*MARKET_DIR.glob("*.py"), SRC_DIR / "config.py"]
    hex32 = re.compile(r"\b[0-9a-f]{32}\b")
    assigned = re.compile(r"(api_key|token|secret)\s*[:=]\s*[\"'][^\"']{8,}[\"']", re.IGNORECASE)
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert not hex32.search(text), f"possível chave literal em {path.name}"
        assert not assigned.search(text), f"segredo literal em {path.name}"


def test_yfinance_is_not_used_in_production_code_or_dependencies():
    pyproject = (Path(__file__).resolve().parents[2] / "pyproject.toml").read_text(encoding="utf-8")
    assert "yfinance" not in pyproject.lower()
    importer = re.compile(r"^\s*(import|from)\s+yfinance\b", re.MULTILINE)
    for path in SRC_DIR.rglob("*.py"):
        assert not importer.search(path.read_text(encoding="utf-8")), path


# ------------------------------------------------------------------ brapi: só teste, um ticker por chamada
def test_brapi_accepts_one_ticker_and_refuses_lists():
    assert brapi.single_ticker(" petr4 ") == "PETR4"
    for bad in ("PETR4,VALE3", "PETR4 VALE3", "", "DOLAR"):
        with pytest.raises(ValueError):
            brapi.single_ticker(bad)


def test_brapi_quota_stops_at_the_monthly_cap():
    quota = brapi.BrapiQuota(cap=2)
    quota.consume()
    quota.consume()
    with pytest.raises(brapi.BrapiError, match="teto mensal"):
        quota.consume()
    assert brapi.BRAPI_MONTHLY_CAP == 15_000


@respx.mock
async def test_brapi_fetch_is_single_ticker_and_hides_token_in_errors():
    respx.get(f"{brapi.BRAPI_BASE}/PETR4").mock(
        return_value=httpx.Response(200, content=read_fixture("brapi_quote_petr4.json"))
    )
    async with httpx.AsyncClient() as client:
        quote = await brapi.fetch_quote(client, "petr4", "tok-sanitizado", brapi.BrapiQuota())
    assert quote.ticker == "PETR4" and quote.price == q.Decimal("38.45")
    respx.get(f"{brapi.BRAPI_BASE}/VALE3").mock(return_value=httpx.Response(401))
    async with httpx.AsyncClient() as client:
        with pytest.raises(brapi.BrapiError) as info:
            await brapi.fetch_quote(client, "VALE3", "tok-sanitizado", brapi.BrapiQuota())
    assert "tok-sanitizado" not in str(info.value)


def test_brapi_is_never_scheduled_for_production():
    names = {s.source_id for s in build_scheduler(fred_enabled=True).sources()}
    assert not any("brapi" in n or "b3" in n for n in names)
