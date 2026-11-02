"""Agregação OHLC por série e intervalo (`services/candles.py`)."""

from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

from fronteira_fx.models import Quote
from fronteira_fx.schemas_candles import TF_SECONDS, Candle, CandleSeries
from fronteira_fx.services.candles import (
    aggregate_quotes,
    bucket_start,
    candles_series,
    default_window,
    ensure_utc,
    fmt,
    key_filter,
    like_prefix,
    mid_of,
    pair_of,
)
from fronteira_fx.services.quotes import store_quote_draft
from tests.conftest import NOW, add_source, draft

D = Decimal
KEY = "chaco:CDE:USD/PYG:cash"
DAY = datetime(2026, 11, 2, tzinfo=UTC)
T1200 = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)
T1215 = datetime(2026, 11, 2, 12, 15, tzinfo=UTC)
T1300 = datetime(2026, 11, 2, 13, 0, tzinfo=UTC)


def _quote(hh: int, mm: int, buy: str | None, sell: str | None, *, key: str = KEY, mode: str = "real") -> Quote:
    """Cotação em memória (não persistida) para a agregação pura."""
    return Quote(
        id=f"q-{key}-{hh:02d}{mm:02d}",
        source_id="chaco",
        city="CDE",
        base="USD",
        quote="PYG",
        buy=D(buy) if buy is not None else None,
        sell=D(sell) if sell is not None else None,
        modality="cash",
        kind="indicative",
        channel="physical",
        series_key=key,
        captured_at=DAY.replace(hour=hh, minute=mm),
        data_mode=mode,
    )


# Exemplo canônico de §0.4 da spec: 12:01, 12:06, 12:11 (só compra), 12:16.
CANONICAL = [
    _quote(12, 1, "7320", "7350"),
    _quote(12, 6, "7322", "7352"),
    _quote(12, 11, "7318", None),
    _quote(12, 16, "7325", "7355"),
]


# ---- helpers puros ------------------------------------------------------------------------------


def test_ensure_utc_treats_naive_as_utc_and_converts_aware():
    naive = datetime(2026, 11, 2, 12, 7, 31)
    assert ensure_utc(naive) == datetime(2026, 11, 2, 12, 7, 31, tzinfo=UTC)
    minus3 = datetime(2026, 11, 2, 9, 7, 31, tzinfo=timezone(timedelta(hours=-3)))
    out = ensure_utc(minus3)
    assert out == datetime(2026, 11, 2, 12, 7, 31, tzinfo=UTC) and out.tzinfo is UTC


def test_bucket_start_aligns_to_epoch_utc():
    ts = datetime(2026, 11, 2, 12, 7, 31, tzinfo=UTC)
    assert bucket_start(ts, 900) == T1200
    assert bucket_start(ts, 3600) == T1200
    assert bucket_start(ts, 86400) == DAY
    assert bucket_start(datetime(2026, 11, 2, 12, 7, 31), 900) == T1200  # naive => UTC
    assert bucket_start(ts, 900).tzinfo is UTC
    assert TF_SECONDS == {"15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}


def test_mid_of_uses_both_sides_or_the_one_present():
    assert mid_of(D("7320"), D("7350")) == D("7335")
    assert mid_of(None, D("7350")) == D("7350")
    assert mid_of(D("7320"), None) == D("7320")
    assert mid_of(None, None) is None


def test_fmt_is_the_shared_presentation_formatter():
    assert fmt(D("7335")) == "7335"
    assert fmt(D("7335.123456789")) == "7335.12345679"
    assert fmt(D("5.4310")) == "5.431"
    assert fmt(None) is None


def test_pair_of_reads_the_third_segment():
    assert pair_of("chaco:CDE:USD/PYG:cash") == "USD/PYG"
    assert pair_of("wu:digital:BRL/PYG:transfer:5000:abcdef01") == "BRL/PYG"
    assert pair_of("x") == ""
    assert pair_of("") == ""


def test_key_filter_matches_exact_key_and_contract_suffixes():
    sql = str(key_filter("chaco:CDE:USD/PYG:cash").compile(compile_kwargs={"literal_binds": True}))
    assert "quotes.series_key = 'chaco:CDE:USD/PYG:cash'" in sql
    assert "quotes.series_key LIKE 'chaco:CDE:USD/PYG:cash:%'" in sql


def test_key_filter_escapes_like_wildcards_and_declares_escape():
    # `_` e `%` da chave são literais no LIKE; o `ESCAPE` é declarado para o banco não adivinhar
    assert like_prefix("wu:digital:BRL/PYG:cash_promo") == "wu:digital:BRL/PYG:cash\\_promo:%"
    assert like_prefix("a:b:c/d:x%y\\z") == "a:b:c/d:x\\%y\\\\z:%"
    sql = str(key_filter("wu:digital:BRL/PYG:cash_promo").compile(compile_kwargs={"literal_binds": True}))
    assert "LIKE 'wu:digital:BRL/PYG:cash\\_promo:%' ESCAPE '\\'" in sql


# ---- aggregate_quotes ---------------------------------------------------------------------------


def test_aggregate_canonical_15m_buckets():
    candles = aggregate_quotes(CANONICAL, "15m", "real")
    assert [c.t for c in candles] == [T1200, T1215]
    first, second = candles
    assert isinstance(first, Candle)
    assert (first.o, first.h, first.l, first.c) == (D("7335"), D("7337"), D("7318"), D("7318"))
    assert first.n == 3
    assert first.spread_avg == D("30")
    assert (first.buy_c, first.sell_c) == (D("7318"), D("7352"))  # 12:11 atualiza buy_c, não sell_c
    assert (second.o, second.h, second.l, second.c) == (D("7340"), D("7340"), D("7340"), D("7340"))
    assert second.n == 1
    assert second.spread_avg == D("30")
    assert (second.buy_c, second.sell_c) == (D("7325"), D("7355"))
    assert all(c.data_mode == "real" for c in candles)


def test_aggregate_canonical_1h_single_bucket():
    (c,) = aggregate_quotes(CANONICAL, "1h", "real")
    assert c.t == T1200
    assert (c.o, c.h, c.l, c.c) == (D("7335"), D("7340"), D("7318"), D("7340"))
    assert c.n == 4
    assert c.spread_avg == D("30")
    assert (c.buy_c, c.sell_c) == (D("7325"), D("7355"))
    assert c.data_mode == "real"


def test_candle_json_uses_decimal_strings_and_iso_utc():
    (c,) = aggregate_quotes(CANONICAL, "1h", "real")
    body = c.model_dump(mode="json")
    assert body["t"] == "2026-11-02T12:00:00Z"
    assert body["o"] == "7335" and body["h"] == "7340" and body["l"] == "7318" and body["c"] == "7340"
    assert body["spread_avg"] == "30" and body["buy_c"] == "7325" and body["sell_c"] == "7355"
    assert body["n"] == 4 and body["data_mode"] == "real"


def test_aggregate_emits_no_empty_buckets_and_keeps_ascending_order():
    candles = aggregate_quotes([_quote(12, 1, "7320", "7350"), _quote(13, 1, "7322", "7352")], "15m", "real")
    assert [c.t for c in candles] == [T1200, T1300]


def test_aggregate_ignores_quotes_without_any_side_and_emits_nulls():
    candles = aggregate_quotes([_quote(12, 1, None, None), _quote(12, 2, None, "7350")], "15m", "real")
    assert len(candles) == 1
    c = candles[0]
    assert c.n == 1 and c.o == c.c == D("7350")
    assert c.spread_avg is None and c.buy_c is None and c.sell_c == D("7350")
    assert set(c.model_dump(mode="json")) >= {"spread_avg", "buy_c", "sell_c"}  # nulos sempre emitidos
    assert aggregate_quotes([_quote(12, 1, None, None)], "15m", "real") == []


def test_aggregate_does_not_round_and_carries_data_mode():
    quotes = [_quote(12, 1, "7320.123456789", "7350.987654321", mode="simulation")]
    (c,) = aggregate_quotes(quotes, "1d", "simulation")
    assert c.t == DAY
    assert c.o == D("7335.55555556")  # 8 casas, ROUND_HALF_EVEN, via fmt
    assert c.spread_avg == D("30.86419753")
    assert c.data_mode == "simulation"


# ---- default_window -----------------------------------------------------------------------------


def test_default_window_without_bounds_counts_back_limit_minus_one_buckets():
    assert default_window("1h", None, None, 300, NOW) == (NOW - timedelta(hours=299), NOW)
    assert default_window("15m", None, None, 1, NOW) == (NOW, NOW)


def test_default_window_aligns_start_to_bucket_and_keeps_end():
    start = datetime(2026, 11, 2, 12, 7, tzinfo=UTC)
    assert default_window("15m", start, T1300, 10, NOW) == (T1200, T1300)
    assert default_window("15m", datetime(2026, 11, 2, 12, 7), datetime(2026, 11, 2, 13, 0), 10, NOW) == (T1200, T1300)
    # só `to`: `from` = bucket_start(to) − (limit − 1)·grid
    assert default_window("15m", None, T1300, 4, NOW) == (T1215, T1300)


# ---- candles_series (SQLite em memória) ---------------------------------------------------------


def _store(db, d, when: datetime, *, mode: str = "real") -> None:
    store_quote_draft(db, d, evidence_id=None, data_mode=mode, captured_at=when)


def _seed_chaco(db) -> None:
    add_source(db, "chaco", cities=["CDE"], branches=[("chaco-cde-centro", "CDE")])


def test_candles_series_prefix_matching_and_mode_isolation(db):
    _seed_chaco(db)
    at = DAY.replace(hour=12, minute=1)
    later = DAY.replace(hour=12, minute=2)  # instantes distintos: empate em `captured_at` desempata por `id` (uuid4)
    _store(db, draft("chaco", "USD", "PYG", "7320", "7350", city="CDE"), at)  # chave exata
    _store(
        db, draft("chaco", "USD", "PYG", "7322", "7352", city="CDE", branch_id="chaco-cde-centro"), later
    )  # :@branch
    _store(db, draft("chaco", "USD", "PYG", "9000", "9100", city="CDE", modality="cash_promo"), at)  # outra modalidade
    _store(db, draft("chaco", "USD", "PYG", "1", "1", city="CDE"), at, mode="demo")  # outro modo
    db.flush()

    series = candles_series(db, KEY, "15m", T1200, T1300, 300, "real")
    assert isinstance(series, CandleSeries)
    assert (series.key, series.tf, series.data_mode) == (KEY, "15m", "real")
    assert len(series.candles) == 1
    c = series.candles[0]
    assert c.n == 2 and c.o == D("7335") and c.c == D("7337") and c.h == D("7337") and c.l == D("7335")
    assert (c.buy_c, c.sell_c, c.spread_avg) == (D("7322"), D("7352"), D("30"))

    promo = candles_series(db, "chaco:CDE:USD/PYG:cash_promo", "15m", T1200, T1300, 300, "real")
    assert len(promo.candles) == 1 and promo.candles[0].o == D("9050")

    demo = candles_series(db, KEY, "15m", T1200, T1300, 300, "demo")
    assert demo.data_mode == "demo"
    assert len(demo.candles) == 1 and demo.candles[0].o == D("1")


def test_candles_series_window_is_from_inclusive_to_exclusive(db):
    _seed_chaco(db)
    for q in CANONICAL:
        _store(db, draft("chaco", "USD", "PYG", q.buy, q.sell, city="CDE"), q.captured_at)
    _store(db, draft("chaco", "USD", "PYG", "7000", "7010", city="CDE"), T1300)  # == to: fora
    db.flush()

    series = candles_series(db, KEY, "15m", datetime(2026, 11, 2, 12, 7, tzinfo=UTC), T1300, 300, "real")
    assert [c.t for c in series.candles] == [T1200, T1215]  # from_eff = 12:00 inclui a cotação de 12:01
    assert series.candles[0].n == 3 and series.candles[1].n == 1

    empty = candles_series(db, "x:CDE:USD/PYG:cash", "15m", T1200, T1300, 300, "real")
    assert empty.candles == []


def test_candles_series_limit_keeps_the_tail_in_ascending_order(db):
    _seed_chaco(db)
    for q in CANONICAL:
        _store(db, draft("chaco", "USD", "PYG", q.buy, q.sell, city="CDE"), q.captured_at)
    db.flush()

    one = candles_series(db, KEY, "15m", T1200, T1300, 1, "real")
    assert [c.t for c in one.candles] == [T1215]
    two = candles_series(db, KEY, "15m", T1200, T1300, 2, "real")
    assert [c.t for c in two.candles] == [T1200, T1215]
