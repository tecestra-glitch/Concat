"""Stream da Binance (klines fechadas e bookTicker) sem rede: servidor websocket falso local e relógio simulado.

Cobre: renovação antes das 24 h sem perder velas, ping/pong, limite de 300 conexões novas por 5 min, recuo após
queda, HTTP 451 (desliga, não reconecta), parser (vela aberta fica de fora), gravação em lote e a chave FX_BINANCE_WS.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from http import HTTPStatus
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker
from websockets.asyncio.client import connect as real_connect
from websockets.asyncio.server import ServerConnection, serve
from websockets.exceptions import ConnectionClosed

from fronteira_fx.config import Settings
from fronteira_fx.market import binance_ws as bw
from fronteira_fx.market import quotes as q
from fronteira_fx.models import MarketBookTop, MarketCandle
from fronteira_fx.services import worker

T0 = datetime(2026, 11, 4, 0, 0, tzinfo=UTC)
MS = 1000


class SimClock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, delta: timedelta) -> None:
        self.now += delta


def ws_settings(**env: Any) -> Settings:
    base: dict[str, Any] = {
        "database_url": "sqlite://",
        "auto_create_schema": True,
        "data_mode": "real",
        "seed_demo": False,
        "seed_knowledge": False,
        "FX_BINANCE_WS_SYMBOLS": "BTCUSDT",
    }
    base.update(env)
    return Settings(_env_file=None, **base)


def kline_msg(symbol: str, open_ms: int, *, closed: bool, interval: str = "5m", close: str = "100.5") -> str:
    lower = symbol.lower()
    return json.dumps(
        {
            "stream": f"{lower}@kline_{interval}",
            "data": {
                "e": "kline",
                "E": open_ms + 1,
                "s": symbol,
                "k": {
                    "t": open_ms,
                    "T": open_ms + 5 * 60 * MS - 1,
                    "s": symbol,
                    "i": interval,
                    "o": "100.0",
                    "c": close,
                    "h": "101.25",
                    "l": "99.5",
                    "v": "12.3",
                    "x": closed,
                },
            },
        }
    )


def book_msg(symbol: str, update_id: int, bid: str = "100.1") -> str:
    return json.dumps(
        {
            "stream": f"{symbol.lower()}@bookTicker",
            "data": {"u": update_id, "s": symbol, "b": bid, "B": "2.5", "a": "100.2", "A": "1.75"},
        }
    )


class FakeBinance:
    """Servidor websocket local. `mode`: ok (mantém a conexão), drop (fecha logo), 451 (recusa o handshake)."""

    def __init__(self, mode: str = "ok") -> None:
        self.mode = mode
        self.handshakes: list[float] = []  # monotonic, uma entrada por handshake recebido
        self.conns: list[ServerConnection] = []
        self.pong_ok = False

    async def handler(self, ws: ServerConnection) -> None:
        self.handshakes.append(time.monotonic())
        self.conns.append(ws)
        if self.mode == "drop":
            await ws.close()
            return
        if self.mode == "ok" and not self.pong_ok:
            # o servidor pinga o cliente; o cliente precisa responder com pong (automático na biblioteca)
            waiter = await ws.ping(b"hb")
            await asyncio.wait_for(waiter, timeout=2)
            self.pong_ok = True
        try:
            async for _ in ws:
                pass
        except ConnectionClosed:
            pass

    def process_request(self, connection: ServerConnection, request: Any) -> Any:
        if self.mode == "451":
            self.handshakes.append(time.monotonic())
            return connection.respond(HTTPStatus.UNAVAILABLE_FOR_LEGAL_REASONS, "bloqueio regional\n")
        return None


@pytest.fixture
async def fake_server() -> AsyncIterator[Callable[..., Any]]:
    servers: list[Any] = []

    async def start(mode: str = "ok") -> tuple[FakeBinance, str]:
        fake = FakeBinance(mode)
        server = await serve(fake.handler, "127.0.0.1", 0, process_request=fake.process_request)
        servers.append(server)
        port = server.sockets[0].getsockname()[1]
        return fake, f"ws://127.0.0.1:{port}/stream"

    yield start
    for server in servers:
        server.close()
        await server.wait_closed()


async def wait_until(pred: Callable[[], bool], timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while not pred():
        if time.monotonic() > deadline:
            raise AssertionError("condição não ocorreu a tempo")
        await asyncio.sleep(0.01)


# ------------------------------------------------------------------ unidades puras


def test_limiter_allows_300_new_connections_per_5_min_and_no_more() -> None:
    limiter = bw.ConnectionRateLimiter()
    t = T0
    for _ in range(300):
        assert limiter.delay_s(t) == 0
        limiter.record(t)
    # a 301ª conexão só abre quando a mais antiga sair da janela de 5 min
    assert limiter.delay_s(t) == pytest.approx(300.0)
    assert limiter.delay_s(t + timedelta(seconds=299)) == pytest.approx(1.0)
    assert limiter.delay_s(t + timedelta(seconds=300)) == 0


def test_limiter_never_exceeds_limit_in_any_window_under_saturation() -> None:
    limiter = bw.ConnectionRateLimiter(max_new=300, window=timedelta(minutes=5))
    now = T0
    opened: list[datetime] = []
    for _ in range(2000):  # tenta abrir sem parar
        now = now + timedelta(seconds=limiter.delay_s(now))
        limiter.record(now)
        opened.append(now)
    for i, start in enumerate(opened):
        in_window = [s for s in opened if start <= s < start + timedelta(minutes=5)]
        assert len(in_window) <= 300, (i, len(in_window))


def test_backoff_doubles_and_caps() -> None:
    assert [bw.backoff_delay(a, 1.0, 10.0) for a in range(1, 7)] == [1.0, 2.0, 4.0, 8.0, 10.0, 10.0]
    with pytest.raises(ValueError):
        bw.backoff_delay(0)


def test_build_url_lists_kline_and_bookticker_per_symbol() -> None:
    url = bw.build_url("wss://data-stream.binance.vision/stream", ["BTCUSDT", "USDTBRL"], "5m")
    assert url == (
        "wss://data-stream.binance.vision/stream?streams="
        "btcusdt@kline_5m/btcusdt@bookTicker/usdtbrl@kline_5m/usdtbrl@bookTicker"
    )


def test_parse_closed_kline_becomes_candle_with_decimals() -> None:
    ev = bw.parse_message(kline_msg("BTCUSDT", 1_700_000_000_000, closed=True, close="100.50"))
    assert isinstance(ev, bw.KlineEvent)
    assert ev.symbol == "BTCUSDT" and ev.interval == "5m"
    assert ev.candle.close == Decimal("100.50")
    assert ev.candle.open_time == datetime.fromtimestamp(1_700_000_000, tz=UTC)
    assert ev.candle.close_time == ev.candle.open_time + timedelta(minutes=5) - timedelta(milliseconds=1)


def test_parse_open_kline_is_ignored() -> None:
    assert bw.parse_message(kline_msg("BTCUSDT", 1_700_000_000_000, closed=False)) is None


def test_parse_bookticker_and_subscription_ack() -> None:
    ev = bw.parse_message(book_msg("BTCUSDT", 42, bid="100.1"))
    assert ev == bw.BookEvent(
        symbol="BTCUSDT",
        update_id=42,
        bid=Decimal("100.1"),
        bid_qty=Decimal("2.5"),
        ask=Decimal("100.2"),
        ask_qty=Decimal("1.75"),
    )
    assert bw.parse_message('{"result": null, "id": 1}') is None


@pytest.mark.parametrize("raw", ["não é json", "[1, 2]", '{"stream":"x","data":{"e":"kline","k":{"x":true}}}'])
def test_parse_malformed_raises_feed_error(raw: str) -> None:
    with pytest.raises(q.FeedFormatError):
        bw.parse_message(raw)


def test_settings_defaults_keep_stream_off() -> None:
    s = Settings(_env_file=None, database_url="sqlite://", seed_demo=False, seed_knowledge=False)
    assert s.binance_ws is False
    assert s.binance_ws_rotate_s == 23 * 3600
    assert s.binance_ws_ping_s == 20.0


def test_rotation_later_than_limit_is_refused(market_factory) -> None:
    with pytest.raises(ValueError):
        bw.BinanceStream(market_factory, ws_settings(), rotate_after=timedelta(hours=24))


# ------------------------------------------------------------------ gravação em lote


def test_flush_writes_closed_candles_once_and_upserts_book(market_factory: sessionmaker[Session]) -> None:
    buf = bw.PendingBuffer()
    c = bw.parse_message(kline_msg("BTCUSDT", 1_700_000_000_000, closed=True))
    assert isinstance(c, bw.KlineEvent)
    buf.add_candle("BTC/USDT", "5m", c.candle)
    buf.add_candle("BTC/USDT", "5m", c.candle)  # mesma vela duas vezes: deduplicada no buffer
    buf.set_book("BTC/USDT", bw.parse_message(book_msg("BTCUSDT", 7, bid="100.1")))  # type: ignore[arg-type]
    buf.set_book("BTC/USDT", bw.parse_message(book_msg("BTCUSDT", 8, bid="100.3")))  # type: ignore[arg-type]
    now = T0

    first = bw.flush_buffer(buf, market_factory, "real", now)
    assert first == bw.FlushResult(candles_added=1, books_written=1)
    assert len(buf) == 0
    # regravar a mesma vela (ex.: sobreposição na renovação) não duplica
    buf.add_candle("BTC/USDT", "5m", c.candle)
    again = bw.flush_buffer(buf, market_factory, "real", now)
    assert again.candles_added == 0

    with market_factory() as s:
        assert s.scalar(select(func.count()).select_from(MarketCandle)) == 1
        book = s.get(MarketBookTop, ("BTCUSDT", "real"))
        assert book is not None and book.bid == Decimal("100.3") and book.update_id == 8


def test_flush_keeps_rows_per_data_mode(market_factory: sessionmaker[Session]) -> None:
    buf = bw.PendingBuffer()
    c = bw.parse_message(kline_msg("BTCUSDT", 1_700_000_000_000, closed=True))
    assert isinstance(c, bw.KlineEvent)
    buf.add_candle("BTC/USDT", "5m", c.candle)
    bw.flush_buffer(buf, market_factory, "simulation", T0)
    with market_factory() as s:
        assert s.scalar(select(MarketCandle.data_mode)) == "simulation"


# ------------------------------------------------------------------ servidor falso


async def test_rotation_before_24h_loses_no_closed_candle(fake_server, market_factory) -> None:
    fake, url = await fake_server("ok")
    clock = SimClock(T0)
    stream = bw.BinanceStream(
        market_factory,
        ws_settings(),
        clock=clock,
        url=url,
        rotate_after=timedelta(hours=23),
        overlap_s=0.1,
        flush_s=0.05,
        tick_s=0.01,
        backoff_base_s=0.01,
    )
    stop = asyncio.Event()
    task = asyncio.create_task(stream.run(stop))
    await wait_until(lambda: len(fake.conns) == 1)

    # candle A e bookTicker na primeira conexão; uma vela aberta não entra
    await fake.conns[0].send(kline_msg("BTCUSDT", _ms(T0), closed=True, close="100.1"))
    await fake.conns[0].send(kline_msg("BTCUSDT", _ms(T0) + 5 * 60 * MS, closed=False))
    await fake.conns[0].send(book_msg("BTCUSDT", 1))

    # 22 h 59 min: ainda não renova
    clock.advance(timedelta(hours=22, minutes=59))
    await asyncio.sleep(0.1)
    assert len(fake.conns) == 1

    # passa de 23 h: abre a segunda conexão antes da queda de 24 h
    clock.advance(timedelta(minutes=2))
    await wait_until(lambda: len(fake.conns) == 2)
    b_open = _ms(T0) + 5 * 60 * MS
    await fake.conns[1].send(kline_msg("BTCUSDT", b_open, closed=True, close="100.2"))
    # sobreposição: a conexão antiga ainda pode receber a mesma vela; a gravação descarta a repetida
    try:
        await fake.conns[0].send(kline_msg("BTCUSDT", b_open, closed=True, close="100.2"))
    except ConnectionClosed:
        pass

    # a antiga é fechada depois da sobreposição; nova vela C só na conexão nova
    await wait_until(lambda: fake.conns[0].state.name == "CLOSED", timeout=3)
    c_open = b_open + 5 * 60 * MS
    await fake.conns[1].send(kline_msg("BTCUSDT", c_open, closed=True, close="100.3"))

    await wait_until(lambda: _count_candles(market_factory) == 3, timeout=3)
    stop.set()
    await asyncio.wait_for(task, timeout=3)

    with market_factory() as s:
        opens = sorted(s.scalars(select(MarketCandle.open_time)))
    assert opens == [
        datetime.fromtimestamp(_ms(T0) / 1000, tz=UTC),
        datetime.fromtimestamp(b_open / 1000, tz=UTC),
        datetime.fromtimestamp(c_open / 1000, tz=UTC),
    ]
    assert stream.connections == 2
    assert stream.malformed == 0


def _ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def _count_candles(factory: sessionmaker[Session]) -> int:
    with factory() as s:
        return int(s.scalar(select(func.count()).select_from(MarketCandle)) or 0)


async def test_server_ping_gets_pong_and_client_pings_every_20_s(fake_server, market_factory) -> None:
    fake, url = await fake_server("ok")
    calls: list[dict[str, Any]] = []

    async def spy_connect(u: str, **kwargs: Any):
        calls.append(kwargs)
        return await real_connect(u, **kwargs)

    stream = bw.BinanceStream(market_factory, ws_settings(), url=url, connect_fn=spy_connect, flush_s=0.05, tick_s=0.01)
    stop = asyncio.Event()
    task = asyncio.create_task(stream.run(stop))
    await wait_until(lambda: fake.pong_ok, timeout=5)
    stop.set()
    await asyncio.wait_for(task, timeout=3)
    assert calls[0]["ping_interval"] == 20.0
    assert calls[0]["ping_timeout"] == 20.0


async def test_http_451_disables_source_without_retry(fake_server, market_factory) -> None:
    fake, url = await fake_server("451")
    stream = bw.BinanceStream(market_factory, ws_settings(), url=url, flush_s=0.05, backoff_base_s=0.01)
    stop = asyncio.Event()
    task = asyncio.create_task(stream.run(stop))
    await asyncio.wait_for(task, timeout=3)  # a tarefa termina sozinha: a fonte está desligada
    assert stream.disabled_reason is not None and "451" in stream.disabled_reason
    assert len(fake.handshakes) == 1  # nenhuma nova tentativa, nenhum contorno


async def test_reconnect_is_paced_by_limiter_and_backoff(fake_server, market_factory) -> None:
    fake, url = await fake_server("drop")
    window = timedelta(seconds=1)
    stream = bw.BinanceStream(
        market_factory,
        ws_settings(),
        url=url,
        flush_s=0.05,
        tick_s=0.01,
        backoff_base_s=0.01,
        limiter=bw.ConnectionRateLimiter(max_new=3, window=window),
    )
    stop = asyncio.Event()
    task = asyncio.create_task(stream.run(stop))
    await asyncio.sleep(1.6)
    stop.set()
    await asyncio.wait_for(task, timeout=3)
    stamps = fake.handshakes
    assert len(stamps) >= 4
    # nunca mais de 3 conexões novas em 1 s (folga de 50 ms por latência de entrega)
    for i in range(len(stamps) - 3):
        assert stamps[i + 3] - stamps[i] >= window.total_seconds() - 0.05, (i, stamps[i + 3] - stamps[i])


# ------------------------------------------------------------------ worker


async def test_worker_starts_stream_only_with_flag(monkeypatch, tmp_path) -> None:
    started: list[bool] = []

    class SpyStream:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            started.append(True)

        async def run(self, stop: asyncio.Event) -> None:
            await stop.wait()

    async def nothing(*args: Any, **kwargs: Any) -> Any:
        return []

    monkeypatch.setattr(worker, "BinanceStream", SpyStream)
    monkeypatch.setattr(worker.Collector, "run_once", nothing)
    monkeypatch.setattr(worker.Collector, "process_tasks", lambda self: _zero())
    monkeypatch.setattr(worker.Collector, "prune_events", lambda self: 0)
    monkeypatch.setattr(worker.MarketPoller, "run_once", nothing)

    off = ws_settings(database_url="sqlite://")
    await worker.run_loop(off, iterations=1)
    assert started == []

    monkeypatch.setenv("FX_BINANCE_WS", "1")
    on = Settings(_env_file=None, database_url="sqlite://", seed_demo=False, seed_knowledge=False)
    assert on.binance_ws is True
    await worker.run_loop(on, iterations=1)
    assert started == [True]


async def _zero() -> int:
    return 0
