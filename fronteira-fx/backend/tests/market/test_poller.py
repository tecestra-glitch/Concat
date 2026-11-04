"""Sondagem do módulo market com HTTP mockado (respx): piso de 60 s, requisição condicional, recuo, bloqueio."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import respx
from sqlalchemy import func, select

from fronteira_fx.market import quotes as q
from fronteira_fx.market import vol
from fronteira_fx.market.news import FEEDS, FEEDS_BY_ID
from fronteira_fx.market.service import FX_SOURCE, MarketPoller
from fronteira_fx.models import MarketCandle, MarketQuote, NewsItem
from fronteira_fx.services import events as events_svc

from .conftest import market_settings, read_fixture

T0 = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)
FEED_BODY = {
    "investinglive": "rss_investinglive.xml",
    "infomoney": "rss_infomoney.xml",
    "infomoney-economia": "rss_infomoney_economia_vazio.xml",
    "infomoney-mercados": "rss_infomoney_mercados_vazio.xml",
    "agencia-brasil-economia": "rss_agencia_brasil.xml",
    "bcb-copom-comunicados": "atom_bcb_copom.xml",
    "bcb-copom-atas": "atom_bcb_atas.xml",
    "mercopress-paraguay": "rss_mercopress_paraguay.xml",
    "mercopress-economy": "rss_mercopress_economy.xml",
}


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def make_poller(factory, clock: Clock, *, keep: set[str] | None = None, data_mode: str = "real") -> MarketPoller:
    poller = MarketPoller(factory, market_settings(data_mode), clock=clock)
    for source in poller.scheduler.sources():
        if keep is not None and source.source_id not in keep:
            poller.scheduler.remove_source(source.source_id)
    return poller


def feed_route(feed_id: str):
    return respx.get(FEEDS_BY_ID[feed_id].url).mock(
        return_value=httpx.Response(200, content=read_fixture(FEED_BODY[feed_id]), headers={"ETag": '"v1"'})
    )


@respx.mock
async def test_feeds_are_polled_only_when_due_never_inside_the_60_seconds(market_factory):
    clock = Clock(T0)
    for feed in FEEDS:
        feed_route(feed.feed_id)
    poller = make_poller(market_factory, clock, keep={f.feed_id for f in FEEDS})
    try:
        first = await poller.run_once()
        assert len(first) == len(FEEDS) and all(r.ok for r in first)

        clock.now = T0 + timedelta(seconds=30)
        assert await poller.run_once() == []  # ainda dentro do piso: nenhuma requisição

        clock.now = T0 + timedelta(seconds=60)
        second = await poller.run_once()
        polled = {r.source_id for r in second}
        assert {"infomoney", "infomoney-economia", "infomoney-mercados", "agencia-brasil-economia"} <= polled
        assert "bcb-copom-comunicados" not in polled and "mercopress-economy" not in polled  # intervalo de 300 s

        calls = {str(c.request.url): 0 for c in respx.calls}
        for c in respx.calls:
            calls[str(c.request.url)] += 1
        assert calls[FEEDS_BY_ID["infomoney"].url] == 2
        assert calls[FEEDS_BY_ID["bcb-copom-comunicados"].url] == 1
    finally:
        await poller.aclose()


@respx.mock
async def test_second_poll_sends_validators_and_304_means_nothing_new(market_factory):
    clock = Clock(T0)
    seen_headers: list[str | None] = []

    def responder(request: httpx.Request) -> httpx.Response:
        seen_headers.append(request.headers.get("If-None-Match"))
        if len(seen_headers) == 1:
            return httpx.Response(200, content=read_fixture("rss_infomoney.xml"), headers={"ETag": '"v1"'})
        return httpx.Response(304)

    respx.get(FEEDS_BY_ID["infomoney"].url).mock(side_effect=responder)
    poller = make_poller(market_factory, clock, keep={"infomoney"})
    try:
        first = await poller.run_once()
        clock.now = T0 + timedelta(seconds=60)
        second = await poller.run_once()
    finally:
        await poller.aclose()
    assert seen_headers == [None, '"v1"']
    assert first[0].changed is True and second[0].ok and second[0].changed is False
    with market_factory() as s:
        assert s.scalar(select(func.count(NewsItem.id))) == 3  # o 304 não gravou nada


@respx.mock
async def test_error_backs_off_and_retries_later(market_factory):
    clock = Clock(T0)
    respx.get(FEEDS_BY_ID["agencia-brasil-economia"].url).mock(return_value=httpx.Response(500))
    poller = make_poller(market_factory, clock, keep={"agencia-brasil-economia"})
    try:
        first = await poller.run_once()
        assert first[0].ok is False and "HTTP 500" in (first[0].error or "")
        clock.now = T0 + timedelta(seconds=60)
        assert await poller.run_once() == []  # recuo: 60 s × 2² com jitter ±15 %, nunca antes de 60 s
        clock.now = T0 + timedelta(seconds=400)
        assert len(await poller.run_once()) == 1
    finally:
        await poller.aclose()


@respx.mock
async def test_rate_limit_from_binance_is_blocked_and_waits_longer(market_factory):
    clock = Clock(T0)
    respx.get(url__startswith=f"{q.BINANCE_BASE}/api/v3/ticker/24hr").mock(return_value=httpx.Response(429))
    poller = make_poller(market_factory, clock, keep={"binance-ticker"})
    try:
        result = await poller.run_once()
        assert result[0].ok is False and "429" in (result[0].error or "")
        source = poller.scheduler.get("binance-ticker")
        assert source.next_run_at is not None and source.next_run_at >= T0 + timedelta(seconds=120)
        clock.now = T0 + timedelta(seconds=60)
        assert await poller.run_once() == []
    finally:
        await poller.aclose()


@respx.mock
async def test_demo_and_simulation_never_touch_the_network(market_factory):
    clock = Clock(T0)
    for feed in FEEDS:
        feed_route(feed.feed_id)
    for mode in ("demo", "simulation"):
        poller = make_poller(market_factory, clock, data_mode=mode)
        try:
            assert await poller.run_once() == []
        finally:
            await poller.aclose()
    assert respx.calls.call_count == 0


@respx.mock
async def test_frankfurter_and_bcb_write_references_and_report_change(market_factory):
    clock = Clock(T0)
    respx.get(url__startswith=q.FRANKFURTER_URL).mock(
        return_value=httpx.Response(200, content=read_fixture("frankfurter_v2_rates.json"))
    )

    def bcb(request: httpx.Request) -> httpx.Response:
        code = request.url.path.split("sgs.")[1].split("/")[0]
        name = {
            "1": "bcb_sgs_1_ultimos2.json",
            "10813": "bcb_sgs_10813_ultimos2.json",
            "432": "bcb_sgs_432_ultimo.json",
        }[code]
        return httpx.Response(200, content=read_fixture(name))

    respx.route(url__startswith="https://api.bcb.gov.br/").mock(side_effect=bcb)
    poller = make_poller(market_factory, clock, keep={FX_SOURCE, "bcb-sgs"})
    try:
        first = await poller.run_once()
        assert all(r.ok for r in first) and all(r.changed for r in first)
        clock.now = T0 + timedelta(seconds=900)
        second = await poller.run_once()
        assert all(r.ok and not r.changed for r in second)  # mesmo valor e mesma data: sem mudança
    finally:
        await poller.aclose()
    with market_factory() as s:
        rows = {r.instrument: r for r in s.scalars(select(MarketQuote))}
        assert {"USD/BRL", "USD/PYG", "USD/ARS", "EUR/USD", "PTAX venda", "PTAX compra", "Selic meta"} <= set(rows)
        assert rows["Selic meta"].price == Decimal("13.75")
        assert rows["USD/PYG"].kind == "fx_reference" and rows["USD/PYG"].source == "frankfurter"


@respx.mock
async def test_binance_candles_store_only_closed_candles_and_no_alert_on_quiet_data(market_factory):
    clock = Clock(datetime.fromtimestamp(1793800000, tz=UTC))
    respx.route(url__startswith=f"{q.BINANCE_BASE}/api/v3/klines").mock(
        return_value=httpx.Response(200, content=read_fixture("binance_klines_usdtbrl_5m.json"))
    )
    poller = make_poller(market_factory, clock, keep={"binance-candles"})
    try:
        result = await poller.run_once()
    finally:
        await poller.aclose()
    assert result[0].ok is True
    with market_factory() as s:
        count = s.scalar(
            select(func.count(MarketCandle.id)).where(
                MarketCandle.instrument == "USDT/BRL", MarketCandle.interval == "5m"
            )
        )
        assert count == 3
        assert events_svc.replay(s, 0, data_mode="real") == []  # 3 velas = insufficient_data: nenhum alerta


def test_alert_event_is_emitted_once_per_transition(market_factory):
    clock = Clock(T0)
    poller = make_poller(market_factory, clock, keep=set())
    snap = vol.VolatilitySnapshot(
        instrument="USDT/BRL",
        status="ok",
        as_of=T0,
        last_move_pct=Decimal("1.5"),
        regime="muito_alta",
        alert=True,
        reasons=("movimento_acima_de_3x_ewma",),
    )
    with market_factory() as s:
        poller._maybe_alert(s, snap, T0)
        poller._maybe_alert(s, snap, T0)  # mesma situação: nada novo
        s.commit()
    with market_factory() as s:
        events = events_svc.replay(s, 0, data_mode="real")
    assert [e.type for e in events] == ["market.volatility_alert"]
    assert events[0].payload["instrument"] == "USDT/BRL" and events[0].payload["regime"] == "muito_alta"
    assert events[0].payload["last_move_pct"] == "1.5"
