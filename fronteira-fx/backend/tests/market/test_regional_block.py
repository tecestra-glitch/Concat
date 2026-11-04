"""HTTP 451 (bloqueio regional) desliga a fonte naquela região: a primeira resposta 451 registra o bloqueio, a fonte
sai do agendamento e nenhuma rodada seguinte faz HTTP (sem contorno e sem nova tentativa). Transporte mockado."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx

from fronteira_fx.config import Settings
from fronteira_fx.market import macro
from fronteira_fx.market import quotes as q
from fronteira_fx.market import reference as ref
from fronteira_fx.market.news import FEEDS_BY_ID
from fronteira_fx.market.service import FX_SOURCE, MarketPoller

T0 = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def keyed_settings(**extra) -> Settings:
    return Settings(
        _env_file=None,
        database_url="sqlite://",
        auto_create_schema=True,
        data_mode="real",
        seed_demo=False,
        seed_knowledge=False,
        quotes_lookback_s=10 * 365 * 86400,
        **extra,
    )


def make_poller(factory, clock: Clock, *, keep: set[str], settings: Settings | None = None) -> MarketPoller:
    poller = MarketPoller(factory, settings or keyed_settings(), clock=clock)
    for source in poller.scheduler.sources():
        if source.source_id not in keep:
            poller.scheduler.remove_source(source.source_id)
    return poller


CASES = [
    pytest.param(
        lambda: respx.route(url__startswith=f"{q.BINANCE_BASE}/api/v3/"),
        {"binance-ticker", "binance-candles"},
        None,
        "binance",
        id="binance-data-api",
    ),
    pytest.param(
        lambda: respx.get(FEEDS_BY_ID["infomoney"].url),
        {"infomoney"},
        None,
        "infomoney",
        id="feed-rss",
    ),
    pytest.param(
        lambda: respx.get(url__startswith=q.FRANKFURTER_URL),
        {FX_SOURCE},
        None,
        FX_SOURCE,
        id="frankfurter",
    ),
    pytest.param(
        lambda: respx.get(url__startswith=ref.OXR_URL),
        {ref.OXR_SOURCE},
        {"oxr_app_id": "chave-de-teste-nao-usar"},
        ref.OXR_SOURCE,
        id="open-exchange-rates",
    ),
    pytest.param(
        lambda: respx.get(url__startswith=macro.FRED_URL),
        {macro.FRED_SOURCE},
        {"fred_api_key": "chave-de-teste-nao-usar"},
        macro.FRED_SOURCE,
        id="fred",
    ),
]


@pytest.mark.parametrize(("route_factory", "keep", "extra", "region"), CASES)
@respx.mock
async def test_451_disables_the_source_and_next_rounds_make_no_request(
    market_factory, route_factory, keep, extra, region
):
    route = route_factory().mock(return_value=httpx.Response(451))
    clock = Clock(T0)
    poller = make_poller(market_factory, clock, keep=keep, settings=keyed_settings(**(extra or {})))
    try:
        first = await poller.run_once()
        assert len(first) == 1 and first[0].ok is False and "451" in (first[0].error or "")
        assert poller.gate.is_blocked(region) is not None
        for source_id in keep:
            assert poller.scheduler.get(source_id).enabled is False
            assert poller.scheduler.get(source_id).next_run_at is None
        assert route.call_count == 1 and len(respx.calls) == 1

        clock.now = T0 + timedelta(hours=2)
        assert await poller.run_once() == []  # nada reagendado nesta região
        clock.now = T0 + timedelta(days=2)
        assert await poller.run_once() == []
        assert len(respx.calls) == 1  # nenhuma requisição após o bloqueio, nem para as irmãs da região
    finally:
        await poller.aclose()


@respx.mock
async def test_451_on_binance_candles_stops_the_ticker_too(market_factory):
    """Binance: o bloqueio vale para o host inteiro. Um 451 nas velas também desliga o ticker da mesma região."""
    klines = respx.get(url__startswith=f"{q.BINANCE_BASE}/api/v3/klines").mock(return_value=httpx.Response(451))
    ticker = respx.get(url__startswith=f"{q.BINANCE_BASE}/api/v3/ticker/24hr").mock(return_value=httpx.Response(200))
    clock = Clock(T0)
    poller = make_poller(market_factory, clock, keep={"binance-ticker", "binance-candles"})
    poller.scheduler.get("binance-ticker").next_run_at = T0 + timedelta(seconds=5)  # só as velas vencem em T0
    try:
        first = await poller.run_once()
        assert [r.source_id for r in first] == ["binance-candles"] and first[0].ok is False
        assert klines.call_count == 1 and ticker.call_count == 0
        assert poller.scheduler.get("binance-ticker").enabled is False
        clock.now = T0 + timedelta(hours=1)
        assert await poller.run_once() == []
        assert klines.call_count == 1 and ticker.call_count == 0  # o ticker não é consultado depois do 451
    finally:
        await poller.aclose()
