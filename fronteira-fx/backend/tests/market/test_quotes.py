from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from fronteira_fx.market import quotes as q

from .conftest import read_fixture


def test_binance_ticker_24h_parses_exact_decimals_and_utc_close_time():
    drafts = q.parse_ticker_24h(q.loads_exact(read_fixture("binance_ticker24hr.json").decode()))
    by = {d.instrument: d for d in drafts}
    assert set(by) == {"BTC/USDT", "ETH/USDT", "USDT/BRL"}
    usdt = by["USDT/BRL"]
    assert usdt.kind == "crypto" and usdt.source == "binance"
    assert usdt.price == Decimal("5.51790000")  # lastPrice do fixture, sem arredondar
    assert usdt.change_pct == Decimal("0.876")
    assert isinstance(usdt.price, Decimal) and isinstance(usdt.change_pct, Decimal)
    assert usdt.observed_at.tzinfo is not None and usdt.observed_at.astimezone(UTC) == usdt.observed_at


def test_ticker_rejects_non_list():
    with pytest.raises(q.FeedFormatError):
        q.parse_ticker_24h({"code": 0})


def test_klines_drop_the_still_open_candle():
    data = q.loads_exact(read_fixture("binance_klines_usdtbrl_5m.json").decode())
    # 3 velas: as duas primeiras fecham antes de 12:05 UTC do fixture; a terceira ainda está aberta
    now = datetime.fromtimestamp(1793761900, tz=UTC)
    candles = q.parse_klines(data, "5m", now=now)
    assert len(candles) == 2
    assert candles[0].open == Decimal("5.51150000") and candles[0].close == Decimal("5.51840000")
    assert candles[-1].close_time < now


def test_klines_all_closed_when_now_is_late():
    data = q.loads_exact(read_fixture("binance_klines_usdtbrl_5m.json").decode())
    assert len(q.parse_klines(data, "5m", now=datetime.fromtimestamp(1793800000, tz=UTC))) == 3


def test_frankfurter_rates_keep_exact_decimals_and_derive_eur_usd():
    drafts = q.parse_frankfurter(q.loads_exact(read_fixture("frankfurter_v2_rates.json").decode()))
    by = {d.instrument: d for d in drafts}
    assert set(by) == {"USD/ARS", "USD/BRL", "USD/PYG", "EUR/USD"}
    assert by["USD/BRL"].price == Decimal("5.453")
    assert by["USD/PYG"].price == Decimal("5958")
    assert by["USD/BRL"].kind == "fx_reference" and by["USD/BRL"].change_pct is None
    # EUR por USD = 0,89314 → USD por EUR = 1 / 0,89314
    assert by["EUR/USD"].price == Decimal(1) / Decimal("0.89314")
    assert by["USD/PYG"].observed_at == datetime(2026, 11, 3, tzinfo=UTC)


def test_bcb_series_takes_last_value_and_change_from_previous():
    data = q.loads_exact(read_fixture("bcb_sgs_1_ultimos2.json").decode())
    draft = q.parse_bcb_series(data, "PTAX venda", "USD/BRL PTAX venda (SGS 1)")
    assert draft.price == Decimal("5.4935")
    assert draft.change_pct == (Decimal("5.4935") - Decimal("5.4212")) / Decimal("5.4212") * 100
    # 03/11/2026 em horário de Brasília (-03:00) → 03:00 UTC
    assert draft.observed_at == datetime(2026, 11, 3, 3, 0, tzinfo=UTC)
    assert draft.source == "bcb" and draft.kind == "bcb_series"


def test_bcb_selic_single_value_has_no_change():
    data = q.loads_exact(read_fixture("bcb_sgs_432_ultimo.json").decode())
    draft = q.parse_bcb_series(data, "Selic meta", "Taxa Selic meta")
    assert draft.price == Decimal("13.75") and draft.change_pct is None


def test_bcb_series_refuses_empty_payload():
    with pytest.raises(q.FeedFormatError):
        q.parse_bcb_series([], "PTAX venda", "x")


def test_loads_exact_never_uses_float():
    value = q.loads_exact('{"rate": 0.1}')["rate"]
    assert isinstance(value, Decimal) and value == Decimal("0.1")
    assert json.loads("0.1") == 0.1  # referência: o json padrão perderia a exatidão
