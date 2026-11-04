"""Gerador demo determinístico do pregão (`services/candles_demo.py`, spec §0.9 e §3.3)."""

from __future__ import annotations

import inspect
from datetime import UTC, date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from fronteira_fx.schemas_candles import HouseSession, SessionStats
from fronteira_fx.services import candles_demo
from fronteira_fx.services.candles import bucket_start
from fronteira_fx.services.candles_demo import (
    DEMO_HOUSES,
    demo_candles,
    demo_house_sessions,
    demo_session_stats,
    drift,
    fnv1a,
    lcg,
)

KEY = "chaco:CDE:USD/PYG:cash"
NOW = datetime(2026, 11, 2, 12, 30, tzinfo=UTC)


# ---- primitivas ---------------------------------------------------------------------------------


def test_fnv1a_of_empty_string_is_the_offset_basis():
    assert fnv1a("") == 2166136261


def test_fnv1a_of_single_letter_matches_reference_value():
    assert fnv1a("a") == 0xE40C292C


def test_fnv1a_returns_unsigned_32_bit_value():
    assert 0 <= fnv1a("chaco:CDE:USD/PYG:cash:1h:1") < 2**32


def test_lcg_first_value_matches_reference_sequence():
    r = lcg(1)
    assert r() == 1015568748 / 2**32


def test_lcg_values_stay_in_unit_interval():
    r = lcg(42)
    values = [r() for _ in range(10)]
    assert all(0 <= v < 1 for v in values)


def test_lcg_different_seeds_give_different_first_values():
    assert lcg(7)() != lcg(8)()


def test_drift_stays_within_the_weekly_band():
    values = [drift(i, 3600) for i in range(0, 24 * 7)]
    assert all(0.995 <= v <= 1.005 for v in values)


# ---- velas --------------------------------------------------------------------------------------


def test_demo_candles_1h_returns_50_ordered_candles_ending_at_bucket_of_now():
    candles = demo_candles(KEY, "1h", None, NOW, 50)
    assert len(candles) == 50
    assert candles[-1].t == datetime(2026, 11, 2, 12, 0, tzinfo=UTC)
    times = [c.t for c in candles]
    assert all(a < b for a, b in zip(times, times[1:], strict=False))


def test_demo_candles_respect_ohlc_and_side_invariants():
    candles = demo_candles(KEY, "1h", None, NOW, 50)
    for c in candles:
        o, h, lo, cl = Decimal(c.o), Decimal(c.h), Decimal(c.l), Decimal(c.c)
        assert Decimal(c.l) <= min(o, cl) <= max(o, cl) <= Decimal(c.h)
        assert c.n >= 1
        assert c.buy_c is not None and c.sell_c is not None
        assert Decimal(c.buy_c) < cl < Decimal(c.sell_c)
        assert c.spread_avg is not None
        assert c.data_mode == "demo"
        assert Decimal("5880") < cl < Decimal("6000")
        assert lo <= h


def test_demo_candles_are_deterministic_across_calls():
    first = demo_candles(KEY, "1h", None, NOW, 50)
    second = demo_candles(KEY, "1h", None, NOW, 50)
    assert [c.model_dump() for c in first] == [c.model_dump() for c in second]


def test_demo_candles_differ_between_series():
    own = demo_candles(KEY, "1h", None, NOW, 50)
    other = demo_candles("alberdi:CDE:USD/PYG:cash", "1h", None, NOW, 50)
    assert [c.c for c in own] != [c.c for c in other]


def test_demo_candles_skip_sunday_for_physical_houses():
    candles = demo_candles(KEY, "1d", None, datetime(2026, 11, 2, tzinfo=UTC), 7)
    assert len(candles) == 7
    assert all(c.t.date() != date(2026, 11, 1) for c in candles)


def test_demo_candles_keep_sunday_for_digital_series():
    candles = demo_candles("ueno:digital:USD/PYG:transfer", "1d", None, datetime(2026, 11, 2, tzinfo=UTC), 7)
    assert any(c.t.date() == date(2026, 11, 1) for c in candles)


def test_demo_candles_start_is_inclusive_and_bounds_the_walk():
    start = datetime(2026, 11, 2, 10, 0, tzinfo=UTC)
    candles = demo_candles(KEY, "1h", start, NOW, 300)
    assert [c.t for c in candles] == [
        datetime(2026, 11, 2, 10, 0, tzinfo=UTC),
        datetime(2026, 11, 2, 11, 0, tzinfo=UTC),
        datetime(2026, 11, 2, 12, 0, tzinfo=UTC),
    ]


def test_demo_candles_end_is_exclusive_on_a_bucket_boundary():
    """QA-6: `to` = 12:00Z exato é exclusivo, então a última vela é 11:00 (como no caminho real)."""
    candles = demo_candles("ueno:digital:USD/PYG:transfer", "1h", None, datetime(2026, 11, 2, 12, 0, tzinfo=UTC), 3)
    assert [c.t.hour for c in candles] == [9, 10, 11]
    inside = demo_candles("ueno:digital:USD/PYG:transfer", "1h", None, datetime(2026, 11, 2, 12, 0, 1, tzinfo=UTC), 3)
    assert [c.t.hour for c in inside] == [10, 11, 12]


def test_demo_candles_accept_naive_start_as_utc():
    aware = demo_candles(KEY, "1h", datetime(2026, 11, 2, 10, 0, tzinfo=UTC), NOW, 300)
    naive = demo_candles(KEY, "1h", datetime(2026, 11, 2, 10, 0), NOW, 300)
    assert [c.model_dump() for c in naive] == [c.model_dump() for c in aware]


def test_demo_candles_without_end_use_the_current_bucket():
    candles = demo_candles(KEY, "15m", None, None, 5)
    assert len(candles) == 5
    assert candles[-1].t <= bucket_start(datetime.now(UTC), 900)


# ---- resumo da sessão ---------------------------------------------------------------------------


def test_demo_session_stats_summarises_the_day_of_the_series():
    (stats,) = demo_session_stats([KEY], NOW)
    assert isinstance(stats, SessionStats)
    assert stats.key == KEY
    assert stats.day_start == datetime(2026, 11, 2, 0, 0, tzinfo=ZoneInfo("America/Asuncion"))
    assert stats.n_quotes > 0
    assert stats.houses == 4  # sem o ueno (descontinuado): chaco, alberdi, norte, bonanza
    assert Decimal(stats.low) <= Decimal(stats.open) <= Decimal(stats.high)
    assert Decimal(stats.change_abs) == Decimal(stats.last) - Decimal(stats.open)
    assert stats.last_at.minute % 15 == 14
    assert stats.last_at.second == 59
    assert stats.data_mode == "demo"


def test_demo_session_stats_keeps_order_and_counts_houses_per_pair():
    first, second = demo_session_stats([KEY, "nomad:digital:USD/BRL:transfer"], NOW)
    assert first.key == KEY
    assert second.key == "nomad:digital:USD/BRL:transfer"
    assert second.houses == 1


def test_demo_session_stats_on_sunday_are_empty():
    (stats,) = demo_session_stats([KEY], datetime(2026, 11, 1, 15, 0, tzinfo=UTC))
    assert stats.n_quotes == 0
    assert stats.open is None
    assert stats.houses == 0


# ---- sessões das casas --------------------------------------------------------------------------


def test_demo_house_sessions_follow_demo_houses_order_and_metadata():
    sessions = demo_house_sessions(NOW)
    assert len(sessions) == len(DEMO_HOUSES) == 6  # ueno saiu do monitor demo
    assert [s.source_id for s in sessions] == [
        "demo-chaco",
        "demo-alberdi",
        "demo-norte",
        "demo-bonanza",
        "demo-nomad",
        "demo-bcp",
    ]
    assert sessions[0].name == "Cambios Chaco"
    assert sessions[0].city == "CDE"
    assert [s.source_id for s in sessions if s.reference] == ["demo-bcp"]
    assert all(isinstance(s, HouseSession) for s in sessions)
    assert all(s.data_mode == "demo" for s in sessions)
    assert all(s.status in {"open", "closed", "pre", "unknown"} for s in sessions)


# ---- contrato de pureza do módulo ---------------------------------------------------------------


def test_module_reads_the_clock_in_exactly_one_place():
    assert inspect.getsource(candles_demo).count("datetime.now(") == 1
