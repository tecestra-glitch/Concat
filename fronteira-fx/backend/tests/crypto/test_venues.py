from decimal import Decimal

import httpx
import pytest

from fronteira_fx.crypto.guard import RateLimited, RegionalBlocked, RegionalGate, VenueError
from fronteira_fx.crypto.venues import BinanceVenue, FoxbitVenue, KrakenVenue, OkxVenue
from tests.crypto.helpers import FakeTime, Recorder, json_response

# Respostas pequenas e sanitizadas, no formato documentado de cada exchange.
KRAKEN_TICKER = {
    "error": [],
    "result": {"XXBTZUSD": {"a": ["100.5", "1", "1.000"], "b": ["100.0", "1", "1.000"], "c": ["100.2", "0.1"]}},
}
KRAKEN_DEPTH = {
    "error": [],
    "result": {
        "XXBTZUSD": {
            "asks": [["101", "0.5", 1], ["100.9", "1", 2]],
            "bids": [["99", "2", 1], ["99.5", "1", 1]],
        }
    },
}
FOXBIT_BOOK = {"bids": [["10", "1"], ["9", "1"]], "asks": [{"price": "11", "quantity": "2"}]}
FOXBIT_TICKER = {"last_price": "10.5", "best_bid": "10.4", "best_ask": "10.6"}
OKX_BOOK = {"code": "0", "msg": "", "data": [{"asks": [["101", "1", "0", "1"]], "bids": [["100", "2", "0", "1"]]}]}
OKX_TICKER = {"code": "0", "msg": "", "data": [{"last": "100.2", "bidPx": "100", "askPx": "100.5"}]}
BINANCE_DEPTH = {"lastUpdateId": 1, "bids": [["100", "1"]], "asks": [["101", "1"], ["102", "3"]]}
BINANCE_PRICE = {"symbol": "BTCUSDT", "price": "100.2"}
BINANCE_BOOK = {"symbol": "BTCUSDT", "bidPrice": "100", "bidQty": "1", "askPrice": "100.5", "askQty": "1"}


def _venue(cls, rec: Recorder, t: FakeTime, gate: RegionalGate | None = None):
    return cls(transport=rec.transport, clock=t.clock, sleep=t.sleep, gate=gate)


# ----------------------------------------------------------------------------- Kraken
async def test_kraken_ticker_and_book_parse_and_fee_is_stored():
    rec = Recorder(lambda req: json_response(KRAKEN_TICKER if "Ticker" in req.url.path else KRAKEN_DEPTH))
    t = FakeTime()
    v = _venue(KrakenVenue, rec, t)
    ticker = await v.fetch_ticker("XBTUSD")
    assert (ticker.bid, ticker.ask, ticker.last) == (Decimal("100.0"), Decimal("100.5"), Decimal("100.2"))
    assert rec.requests[0].url.params["pair"] == "XBTUSD"
    book = await v.fetch_order_book("XBTUSD", 10)
    assert book.asks[0].price == Decimal("100.9")  # ordenado do menor preço
    assert book.bids[0].price == Decimal("99.5")
    assert v.fee.taker == Decimal("0.0080")
    fill = await v.vwap("XBTUSD", "buy", Decimal("1"))
    assert fill.net_price is not None and fill.net_price > fill.vwap
    assert all(r.method == "GET" for r in rec.requests)
    await v.aclose()


async def test_kraken_error_array_raises():
    rec = Recorder(lambda req: json_response({"error": ["EQuery:Unknown asset pair"], "result": {}}))
    v = _venue(KrakenVenue, rec, FakeTime())
    with pytest.raises(VenueError, match="Unknown asset pair"):
        await v.fetch_ticker("XBTXXX")
    await v.aclose()


# ----------------------------------------------------------------------------- Foxbit
async def test_foxbit_book_accepts_pairs_and_objects_and_paths_are_per_market():
    rec = Recorder(lambda req: json_response(FOXBIT_BOOK if "orderbook" in req.url.path else FOXBIT_TICKER))
    t = FakeTime()
    v = _venue(FoxbitVenue, rec, t)
    book = await v.fetch_order_book("BTCBRL", 5)
    assert rec.requests[0].url.path == "/rest/v3/markets/btcbrl/orderbook"
    assert rec.requests[0].url.params["depth"] == "5"
    assert book.asks[0].qty == Decimal("2")
    ticker = await v.fetch_ticker("btcbrl")
    assert ticker.last == Decimal("10.5") and ticker.ask == Decimal("10.6")
    assert v.fee.taker is None  # não confirmada: nunca zero
    await v.aclose()


async def test_foxbit_book_limit_is_ten_requests_per_two_seconds():
    rec = Recorder(lambda req: json_response(FOXBIT_BOOK))
    t = FakeTime()
    v = _venue(FoxbitVenue, rec, t)
    for _ in range(11):
        await v.fetch_order_book("btcbrl")
    assert len(rec.requests) == 11
    assert t.sleeps == [pytest.approx(2.0)]  # a 11ª espera a janela de 2 s
    await v.aclose()


async def test_foxbit_rejects_symbol_that_could_escape_the_path():
    rec = Recorder(lambda req: json_response(FOXBIT_BOOK))
    v = _venue(FoxbitVenue, rec, FakeTime())
    with pytest.raises(VenueError):
        await v.fetch_order_book("../orders")
    assert rec.requests == []
    await v.aclose()


# ----------------------------------------------------------------------------- OKX
async def test_okx_book_and_ticker_parse():
    rec = Recorder(lambda req: json_response(OKX_BOOK if "books" in req.url.path else OKX_TICKER))
    v = _venue(OkxVenue, rec, FakeTime())
    book = await v.fetch_order_book("BTC-USDT", 20)
    assert rec.requests[0].url.params["instId"] == "BTC-USDT"
    assert book.bids[0].price == Decimal("100")
    ticker = await v.fetch_ticker("BTC-USDT")
    assert ticker.bid == Decimal("100") and ticker.ask == Decimal("100.5")
    assert v.fee.taker is None
    await v.aclose()


async def test_okx_nonzero_code_raises():
    rec = Recorder(lambda req: json_response({"code": "51001", "msg": "Instrument ID does not exist", "data": []}))
    v = _venue(OkxVenue, rec, FakeTime())
    with pytest.raises(VenueError, match="51001"):
        await v.fetch_order_book("NOPE-USDT")
    await v.aclose()


# ----------------------------------------------------------------------------- Binance
async def test_binance_uses_data_api_host_and_parses_book_and_ticker():
    def handler(req):
        if req.url.path == "/api/v3/depth":
            return json_response(BINANCE_DEPTH)
        if req.url.path == "/api/v3/ticker/price":
            return json_response(BINANCE_PRICE)
        return json_response(BINANCE_BOOK)

    rec = Recorder(handler)
    v = _venue(BinanceVenue, rec, FakeTime())
    book = await v.fetch_order_book("btcusdt", 100)
    assert rec.requests[0].url.host == "data-api.binance.vision"
    assert book.asks[0].price == Decimal("101")
    ticker = await v.fetch_ticker("BTCUSDT")
    assert ticker.last == Decimal("100.2") and ticker.bid == Decimal("100")
    assert v.fee.maker == Decimal("0.0010") and v.fee.taker == Decimal("0.0010")
    fill = await v.vwap("BTCUSDT", "buy", Decimal("1"))
    assert fill.vwap == Decimal("101")
    assert fill.net_price == Decimal("101") * Decimal("1.0010")
    await v.aclose()


async def test_binance_429_backs_off_using_retry_after_then_succeeds():
    responses = iter([
        httpx.Response(429, headers={"Retry-After": "2"}),
        json_response(BINANCE_DEPTH),
    ])
    rec = Recorder(lambda req: next(responses))
    t = FakeTime()
    v = _venue(BinanceVenue, rec, t)
    book = await v.fetch_order_book("BTCUSDT", 10)
    assert len(rec.requests) == 2
    assert 2.0 in t.sleeps
    assert book.bids[0].qty == Decimal("1")
    await v.aclose()


async def test_binance_429_without_retry_after_uses_exponential_backoff_then_gives_up():
    rec = Recorder(lambda req: httpx.Response(429))
    t = FakeTime()
    v = _venue(BinanceVenue, rec, t)
    with pytest.raises(RateLimited):
        await v.fetch_order_book("BTCUSDT", 10)
    assert len(rec.requests) == 4  # 1 + 3 tentativas
    assert t.sleeps == [1.0, 2.0, 4.0]
    await v.aclose()


async def test_binance_418_stops_the_venue_until_the_ban_expires():
    banned = {"on": True}

    def handler(req):
        if banned["on"]:
            return httpx.Response(418, headers={"Retry-After": "300"})
        return json_response(BINANCE_DEPTH)

    rec = Recorder(handler)
    t = FakeTime()
    v = _venue(BinanceVenue, rec, t)
    with pytest.raises(RateLimited) as first:
        await v.fetch_order_book("BTCUSDT", 10)
    assert first.value.retry_at == pytest.approx(t.now + 300)
    assert len(rec.requests) == 1
    with pytest.raises(RateLimited):  # ainda banido: nenhuma requisição nova
        await v.fetch_order_book("BTCUSDT", 10)
    assert len(rec.requests) == 1
    t.now += 301
    banned["on"] = False
    await v.fetch_order_book("BTCUSDT", 10)
    assert len(rec.requests) == 2
    await v.aclose()


async def test_binance_weight_header_pauses_before_next_request():
    rec = Recorder(lambda req: json_response(BINANCE_DEPTH, headers={"X-MBX-USED-WEIGHT-1M": "5500"}))
    t = FakeTime()
    v = _venue(BinanceVenue, rec, t)
    await v.fetch_order_book("BTCUSDT", 10)
    assert t.sleeps == []
    await v.fetch_order_book("BTCUSDT", 10)
    assert t.sleeps and t.sleeps[0] == pytest.approx(60.0)
    await v.aclose()


def test_binance_depth_cost_follows_weight_table():
    from fronteira_fx.crypto.venues import binance_depth_weight

    assert [binance_depth_weight(n) for n in (5, 100, 101, 500, 501, 1000)] == [5, 5, 25, 25, 50, 50]


# ----------------------------------------------------------------------------- 451 e bloqueio regional
@pytest.mark.parametrize("cls", [KrakenVenue, FoxbitVenue, OkxVenue, BinanceVenue])
async def test_http_451_disables_source_and_never_retries_or_switches_host(cls):
    rec = Recorder(lambda req: httpx.Response(451))
    gate = RegionalGate()
    t = FakeTime()
    v = _venue(cls, rec, t, gate=gate)

    async def call():
        if cls is BinanceVenue:
            await v.fetch_ticker("BTCUSDT")
        else:
            await v.fetch_order_book("BTCUSDT")

    with pytest.raises(RegionalBlocked):
        await call()
    assert gate.is_blocked(cls.name) is not None
    assert len(rec.requests) == 1
    # Fonte desligada: nova chamada nem sai da máquina.
    with pytest.raises(RegionalBlocked):
        await call()
    assert len(rec.requests) == 1
    assert {r.url.host for r in rec.requests} == {v.client._client.base_url.host}
    await v.aclose()


async def test_non_json_body_is_a_venue_error_not_a_crash():
    rec = Recorder(lambda req: httpx.Response(200, text="<html>oops</html>"))
    v = _venue(KrakenVenue, rec, FakeTime())
    with pytest.raises(VenueError, match="não é JSON"):
        await v.fetch_ticker("XBTUSD")
    await v.aclose()
