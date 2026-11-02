"""Horários das casas (`services/market_hours.py`): §0.7 e §6.3 da spec, com datetimes fixos."""

import json
from datetime import UTC, datetime
from importlib import resources
from zoneinfo import ZoneInfo

import pytest

from fronteira_fx.schemas_candles import HouseHours
from fronteira_fx.services import market_hours as mh

HOUSES = {"chaco", "alberdi", "norte", "bonanza", "ueno", "nomad", "revolut", "bcp"}


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)


# ---- arquivo de horários -------------------------------------------------------------------------


def test_market_hours_json_is_packaged_with_the_expected_houses():
    assert resources.files("fronteira_fx").joinpath("data/market_hours.json").is_file()
    houses = mh.load_market_hours()
    assert set(houses) == HOUSES
    assert not any(key.startswith("demo-") for key in houses)
    assert mh.load_market_hours() is mh.load_market_hours()


def test_minutes_of_reads_hhmm_and_maps_24_00_to_1440():
    assert mh.minutes_of("07:30") == 450
    assert mh.minutes_of("00:00") == 0
    assert mh.minutes_of("24:00") == 1440


def test_local_midnight_utc_converts_the_local_day_start_to_utc():
    asuncion = ZoneInfo("America/Asuncion")  # UTC-3 em novembro de 2026
    assert mh.local_midnight_utc(datetime(2026, 11, 2, 15, 0), asuncion) == utc(2026, 11, 2, 3, 0)


def test_parse_returns_house_hours_and_accepts_empty_days():
    houses = mh.parse_market_hours('{"x": {"tz": "UTC", "days": [], "opens": "08:00", "closes": "09:00"}}')
    assert houses == {"x": HouseHours(tz="UTC", days=[], opens="08:00", closes="09:00")}


def test_parse_rejects_closes_not_after_opens_naming_the_house():
    text = '{"x": {"tz": "UTC", "days": [1], "opens": "10:00", "closes": "09:00"}}'
    with pytest.raises(ValueError, match=r"market_hours\[x\]") as exc:
        mh.parse_market_hours(text)
    assert "closes deve ser posterior a opens" in str(exc.value)


def _house(**fields) -> str:
    base = {"tz": "UTC", "days": [1], "opens": "08:00", "closes": "09:00"}
    return json.dumps({"x": {**base, **fields}})


@pytest.mark.parametrize("days", [[8], [0], [1, 1]])
def test_parse_rejects_invalid_days(days: list[int]):
    with pytest.raises(ValueError, match=r"market_hours\[x\]"):
        mh.parse_market_hours(_house(days=days))


@pytest.mark.parametrize(
    ("opens", "closes"),
    [("24:00", "24:00"), ("7:30", "17:00"), ("08:00", "25:00"), ("00:00", "00:00")],
)
def test_parse_rejects_malformed_or_out_of_range_hours(opens: str, closes: str):
    with pytest.raises(ValueError, match=r"market_hours\[x\]"):
        mh.parse_market_hours(_house(opens=opens, closes=closes))


def test_parse_rejects_demo_prefixed_keys():
    text = '{"demo-chaco": {"tz": "UTC", "days": [1], "opens": "08:00", "closes": "09:00"}}'
    with pytest.raises(ValueError, match=r"market_hours\[demo-chaco\]"):
        mh.parse_market_hours(text)


# ---- house_status: exemplos de §0.7 ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        # segunda 09:00 local: aberta até 17:00
        (utc(2026, 11, 2, 12, 0), ("open", utc(2026, 11, 2, 10, 30), utc(2026, 11, 2, 20, 0), utc(2026, 11, 2, 20, 0))),
        # segunda 07:15 local: pré-abertura (30 min antes das 07:30)
        (
            utc(2026, 11, 2, 10, 15),
            ("pre", utc(2026, 11, 2, 10, 30), utc(2026, 11, 2, 20, 0), utc(2026, 11, 2, 10, 30)),
        ),
        # domingo 12:00 local: fechada; próxima mudança é a pré-abertura de segunda
        (
            utc(2026, 11, 1, 15, 0),
            ("closed", utc(2026, 11, 2, 10, 30), utc(2026, 11, 2, 20, 0), utc(2026, 11, 2, 10, 0)),
        ),
    ],
)
def test_chaco_matches_spec_examples(now: datetime, expected):
    assert mh.house_status(mh.load_market_hours()["chaco"], now) == expected


def test_digital_always_open_and_missing_hours_are_unknown_without_times():
    now = utc(2026, 11, 2, 12, 0)
    assert mh.house_status(mh.load_market_hours()["ueno"], now) == ("open", None, None, None)
    assert mh.house_status(None, now) == ("unknown", None, None, None)


# ---- house_status: fronteiras e fins de semana ----------------------------------------------------


def test_saturday_chaco_open_and_norte_closed_until_monday():
    now = utc(2026, 11, 7, 15, 0)
    hours = mh.load_market_hours()
    status, _, closes_at, _ = mh.house_status(hours["chaco"], now)
    assert status == "open" and closes_at == utc(2026, 11, 7, 20, 0)
    assert mh.house_status(hours["norte"], now) == (
        "closed",
        utc(2026, 11, 9, 11, 0),
        utc(2026, 11, 9, 20, 0),
        utc(2026, 11, 9, 10, 30),
    )


def test_exactly_at_closing_time_is_closed_and_next_session_is_tuesday():
    # segunda 17:00 local (fechamento de chaco): `closes` é exclusivo
    assert mh.house_status(mh.load_market_hours()["chaco"], utc(2026, 11, 2, 20, 0)) == (
        "closed",
        utc(2026, 11, 3, 10, 30),
        utc(2026, 11, 3, 20, 0),
        utc(2026, 11, 3, 10, 0),
    )


def test_closed_when_days_is_empty():
    hours = HouseHours(tz="UTC", days=[], opens="08:00", closes="09:00")
    assert mh.house_status(hours, utc(2026, 11, 2, 8, 30)) == ("closed", None, None, None)


def test_closes_24_00_ends_at_local_midnight_of_the_next_day():
    hours = HouseHours(tz="UTC", days=[1], opens="20:00", closes="24:00")
    assert mh.house_status(hours, utc(2026, 11, 2, 23, 0)) == (
        "open",
        utc(2026, 11, 2, 20, 0),
        utc(2026, 11, 3, 0, 0),
        utc(2026, 11, 3, 0, 0),
    )


def test_invalid_timezone_is_unknown_even_for_always_open_houses():
    hours = HouseHours(tz="Nope/Zone", days=[1, 2, 3, 4, 5, 6, 7], opens="00:00", closes="24:00")
    assert mh.house_status(hours, utc(2026, 11, 2, 12, 0)) == ("unknown", None, None, None)


def test_naive_now_is_treated_as_utc():
    chaco = mh.load_market_hours()["chaco"]
    assert mh.house_status(chaco, datetime(2026, 11, 2, 12, 0)) == mh.house_status(chaco, utc(2026, 11, 2, 12, 0))


# ---- carregamento e cache -------------------------------------------------------------------------


def test_load_reads_through_read_text_and_is_cached(monkeypatch: pytest.MonkeyPatch):
    text = '{"zzz": {"tz": "UTC", "days": [1,2,3,4,5,6,7], "opens": "00:00", "closes": "24:00"}}'
    monkeypatch.setattr(mh, "_read_text", lambda: text)
    mh.load_market_hours.cache_clear()
    try:
        assert set(mh.load_market_hours()) == {"zzz"}
        assert mh.house_status(mh.load_market_hours()["zzz"], utc(2026, 11, 2, 12, 0))[0] == "open"
    finally:
        mh.load_market_hours.cache_clear()


# ---- house_sessions -------------------------------------------------------------------------------


def test_house_sessions_keeps_order_flags_reference_and_unknown_houses():
    h = mh.load_market_hours()
    sessions = mh.house_sessions(
        utc(2026, 11, 2, 12, 0),
        {"chaco": h["chaco"], "bcp": h["bcp"], "zzz": None},
        "real",
        reference_ids={"bcp"},
    )
    assert [s.source_id for s in sessions] == ["chaco", "bcp", "zzz"]
    chaco, bcp, zzz = sessions
    assert chaco.status == "open" and chaco.city == "CDE"
    assert bcp.reference is True
    assert zzz.status == "unknown" and zzz.name == "zzz" and zzz.reference is False
    assert all(s.data_mode == "real" for s in sessions)
