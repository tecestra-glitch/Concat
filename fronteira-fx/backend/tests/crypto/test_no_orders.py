"""Garantia de somente leitura: falha se algum método ou caminho de ordem, saque ou conta aparecer no pacote."""

import inspect
import re
from pathlib import Path

import httpx

from fronteira_fx.crypto import venues as venues_mod
from fronteira_fx.crypto.venues import VENUES
from tests.crypto.helpers import FakeTime, Recorder, json_response

PKG_DIR = Path(venues_mod.__file__).resolve().parent

ORDER_METHOD = re.compile(r"^(create|place|cancel|submit|amend|withdraw|transfer|send|buy|sell)(_|$)", re.I)
ORDER_TEXT = re.compile(
    r"(create|place|cancel|submit|amend)_?order|/order\b|api/v3/order|api/v5/trade|withdraw|X-MBX-APIKEY|"
    r"privateKey|apiSecret|/sapi/|/fapi/",
    re.I,
)

CANNED = {
    "/0/public/Ticker": {"error": [], "result": {"XBT": {"a": ["1", "1", "1"], "b": ["1", "1", "1"], "c": ["1", "1"]}}},
    "/0/public/Depth": {"error": [], "result": {"XBT": {"asks": [["1", "1", 1]], "bids": [["1", "1", 1]]}}},
    "/rest/v3/markets/btcbrl/orderbook": {"bids": [["1", "1"]], "asks": [["2", "1"]]},
    "/rest/v3/markets/btcbrl/ticker/24hr": {"last_price": "1", "best_bid": "1", "best_ask": "2"},
    "/api/v5/market/books": {"code": "0", "msg": "", "data": [{"asks": [["2", "1"]], "bids": [["1", "1"]]}]},
    "/api/v5/market/ticker": {"code": "0", "msg": "", "data": [{"last": "1", "bidPx": "1", "askPx": "2"}]},
    "/api/v3/depth": {"bids": [["1", "1"]], "asks": [["2", "1"]]},
    "/api/v3/ticker/price": {"symbol": "BTCUSDT", "price": "1"},
    "/api/v3/ticker/bookTicker": {"bidPrice": "1", "askPrice": "2"},
}


def test_no_order_style_public_methods_on_any_venue():
    for cls in VENUES.values():
        for name in dir(cls):
            if name.startswith("_"):
                continue
            assert not ORDER_METHOD.match(name), f"{cls.__name__}.{name} parece método de ordem"


def test_no_order_or_account_text_in_package_source():
    for path in PKG_DIR.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), start=1):
            assert not ORDER_TEXT.search(line), f"{path.name}:{lineno} contém texto de ordem/conta: {line.strip()}"


def test_no_http_method_other_than_get_is_used_in_package():
    for path in PKG_DIR.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"\.(post|put|delete|patch)\(", text), path.name


async def test_every_public_method_only_sends_allowlisted_get_requests():
    def handler(req: httpx.Request) -> httpx.Response:
        return json_response(CANNED[req.url.path])

    for cls in VENUES.values():
        rec = Recorder(handler)
        t = FakeTime()
        venue = cls(transport=rec.transport, sleep=t.sleep, clock=t.clock)
        if cls.name == "kraken":
            await venue.fetch_ticker("XBT")
            await venue.fetch_order_book("XBT")
        elif cls.name == "foxbit":
            await venue.fetch_ticker("btcbrl")
            await venue.fetch_order_book("btcbrl")
        elif cls.name == "okx":
            await venue.fetch_ticker("BTC-USDT")
            await venue.fetch_order_book("BTC-USDT")
        else:
            await venue.fetch_ticker("BTCUSDT")
            await venue.fetch_order_book("BTCUSDT")
        assert rec.requests, cls.name
        for req in rec.requests:
            assert req.method == "GET", (cls.name, req.method)
            assert not ORDER_TEXT.search(req.url.path), (cls.name, req.url.path)
            assert req.url.host in {"api.kraken.com", "api.foxbit.com.br", "www.okx.com", "data-api.binance.vision"}
            assert "X-MBX-APIKEY" not in req.headers
            assert "Authorization" not in req.headers
        await venue.aclose()


def test_venue_classes_are_not_given_order_methods_by_inheritance():
    from fronteira_fx.crypto.venues import CryptoVenue

    own = {n for n, _ in inspect.getmembers(CryptoVenue, predicate=inspect.isfunction)}
    assert not {n for n in own if ORDER_METHOD.match(n)}
