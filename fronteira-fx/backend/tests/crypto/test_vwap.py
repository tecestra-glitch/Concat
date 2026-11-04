from datetime import UTC, datetime
from decimal import Decimal

import pytest

from fronteira_fx.crypto import Level, OrderBook, VenueFee, vwap_for_target

FEE = VenueFee(venue="binance", maker=Decimal("0.001"), taker=Decimal("0.001"), source="teste")
NOW = datetime(2026, 11, 4, tzinfo=UTC)


def _book(bids, asks) -> OrderBook:
    return OrderBook(
        venue="binance",
        symbol="BTCUSDT",
        bids=tuple(Level(Decimal(p), Decimal(q)) for p, q in bids),
        asks=tuple(Level(Decimal(p), Decimal(q)) for p, q in asks),
        fetched_at=NOW,
    )


def test_buy_walks_asks_from_lowest_price():
    book = _book(bids=[("99", "5")], asks=[("102", "1"), ("100", "0.5")])
    fill = vwap_for_target(book, "buy", Decimal("1"), FEE)
    # 0,5 @ 100 + 0,5 @ 102 => 101
    assert fill.vwap == Decimal("101")
    assert fill.filled_qty == Decimal("1")
    assert fill.complete is True
    assert fill.net_price == Decimal("101") * Decimal("1.001")
    assert fill.executable is False


def test_sell_walks_bids_from_highest_price():
    book = _book(bids=[("98", "2"), ("99", "1")], asks=[("100", "5")])
    fill = vwap_for_target(book, "sell", Decimal("2"), FEE)
    # 1 @ 99 + 1 @ 98 => 98,5
    assert fill.vwap == Decimal("98.5")
    assert fill.net_price == Decimal("98.5") * (Decimal(1) - Decimal("0.001"))


def test_incomplete_depth_reports_partial_fill():
    book = _book(bids=[], asks=[("100", "0.25")])
    fill = vwap_for_target(book, "buy", Decimal("1"), FEE)
    assert fill.complete is False
    assert fill.filled_qty == Decimal("0.25")
    assert fill.vwap == Decimal("100")


def test_empty_book_gives_no_vwap():
    fill = vwap_for_target(_book(bids=[], asks=[]), "buy", Decimal("1"), FEE)
    assert fill.vwap is None
    assert fill.net_price is None
    assert fill.filled_qty == 0


def test_unconfirmed_fee_never_becomes_zero():
    no_fee = VenueFee(venue="foxbit", maker=None, taker=None, source="nao confirmada")
    fill = vwap_for_target(_book(bids=[], asks=[("100", "1")]), "buy", Decimal("1"), no_fee)
    assert fill.vwap == Decimal("100")
    assert fill.net_price is None


def test_rejects_non_positive_target():
    with pytest.raises(ValueError):
        vwap_for_target(_book(bids=[], asks=[("100", "1")]), "buy", Decimal("0"), FEE)


def test_decimal_is_exact_no_float_drift():
    book = _book(bids=[], asks=[("0.1", "0.1"), ("0.3", "0.2")])
    fill = vwap_for_target(book, "buy", Decimal("0.3"), FEE)
    # 0,1 @ 0,1 + 0,2 @ 0,3 = 0,01 + 0,06 = 0,07 ; 0,07 / 0,3
    assert fill.vwap == Decimal("0.07") / Decimal("0.3")
