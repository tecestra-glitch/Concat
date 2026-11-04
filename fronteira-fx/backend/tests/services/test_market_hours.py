"""Horários das casas (`services/market_hours.py`): §0.7 e §6.3 da spec, com datetimes fixos."""

import json
from datetime import UTC, datetime
from importlib import resources
from zoneinfo import ZoneInfo

import pytest

from fronteira_fx.schemas_candles import HouseHours, ScheduleWindow
from fronteira_fx.services import market_hours as mh

HOUSES = {"chaco", "maxicambios", "bcp"}


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)


# ---- arquivo de horários -------------------------------------------------------------------------


def test_market_hours_json_is_packaged_with_the_expected_houses():
    assert resources.files("fronteira_fx").joinpath("data/market_hours.json").is_file()
    houses = mh.load_market_hours()
    assert set(houses) == HOUSES
    assert not any(key.startswith("demo-") for key in houses)
    assert mh.load_market_hours() is mh.load_market_hours()


def test_verified_houses_carry_source_and_check_date():
    houses = mh.load_market_hours()
    for key in ("chaco", "maxicambios", "bcp"):
        assert houses[key].verified is True
        assert houses[key].source_url and houses[key].checked_at == "2026-11-04"


def test_packaged_file_lists_only_houses_with_verified_hours():
    # docs/api-contract.md (Pregão): casa sem horário verificado não entra no arquivo; aparece como unknown.
    houses = mh.load_market_hours()
    assert [key for key, hours in houses.items() if hours.verified is not True] == []


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


# ---- house_status: horário verificado do chaco (sede CDE: Adrián Jara) ----------------------------


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        # segunda 09:00 local: aberta das 07:15 às 16:00 local (10:15-19:00 UTC)
        (utc(2026, 11, 2, 12, 0), ("open", utc(2026, 11, 2, 10, 15), utc(2026, 11, 2, 19, 0), utc(2026, 11, 2, 19, 0))),
        # segunda 07:00 local: pré-abertura (15 min antes das 07:15)
        (utc(2026, 11, 2, 10, 0), ("pre", utc(2026, 11, 2, 10, 15), utc(2026, 11, 2, 19, 0), utc(2026, 11, 2, 10, 15))),
        # domingo 12:00 local: fechada (sem janela no domingo); próxima mudança é a pré-abertura de segunda
        (
            utc(2026, 11, 1, 15, 0),
            ("closed", utc(2026, 11, 2, 10, 15), utc(2026, 11, 2, 19, 0), utc(2026, 11, 2, 9, 45)),
        ),
    ],
)
def test_chaco_matches_verified_weekday_hours(now: datetime, expected):
    assert mh.house_status(mh.load_market_hours()["chaco"], now) == expected


def test_verified_around_the_clock_house_is_open_and_missing_hours_are_unknown():
    now = utc(2026, 11, 2, 12, 0)
    around_the_clock = HouseHours(
        tz="America/Asuncion", days=[1, 2, 3, 4, 5, 6, 7], opens="00:00", closes="24:00", verified=True
    )
    assert mh.house_status(around_the_clock, now) == ("open", None, None, None)
    assert mh.house_status(None, now) == ("unknown", None, None, None)

# ---- house_status: fronteiras, sábado à tarde e domingo -------------------------------------------


def test_saturday_afternoon_window_closes_at_13_00_local():
    # sábado: chaco abre 07:15 e fecha 13:00 local (16:00 UTC); `closes` é exclusivo
    hours = mh.load_market_hours()["chaco"]
    assert mh.house_status(hours, utc(2026, 11, 7, 15, 59)) == (
        "open",
        utc(2026, 11, 7, 10, 15),
        utc(2026, 11, 7, 16, 0),
        utc(2026, 11, 7, 16, 0),
    )
    # 13:00 local em ponto: já fechada; a próxima abertura é segunda 07:15 local
    assert mh.house_status(hours, utc(2026, 11, 7, 16, 0)) == (
        "closed",
        utc(2026, 11, 9, 10, 15),
        utc(2026, 11, 9, 19, 0),
        utc(2026, 11, 9, 9, 45),
    )


def test_saturday_pre_open_boundary():
    hours = mh.load_market_hours()["chaco"]
    # sábado 06:44 local: ainda fechada (pré-abertura começa às 06:45)
    assert mh.house_status(hours, utc(2026, 11, 7, 9, 44))[0] == "closed"
    # sábado 06:45 local: pré-abertura
    assert mh.house_status(hours, utc(2026, 11, 7, 9, 45))[0] == "pre"


def test_saturday_after_close_does_not_reopen_until_monday():
    hours = mh.load_market_hours()["chaco"]
    status, opens_at, _, _ = mh.house_status(hours, utc(2026, 11, 7, 17, 0))  # sábado 14:00 local
    assert status == "closed" and opens_at == utc(2026, 11, 9, 10, 15)


def test_sunday_is_closed_for_chaco_and_maxicambios_has_its_own_sunday_window():
    hours = mh.load_market_hours()
    # domingo 11:00 local (14:00 UTC): chaco fechada (sem janela no domingo)
    assert mh.house_status(hours["chaco"], utc(2026, 11, 8, 14, 0))[0] == "closed"
    # maxicambios domingo 10:00 local (13:00 UTC): janela própria de domingo, aberta
    assert mh.house_status(hours["maxicambios"], utc(2026, 11, 8, 13, 0))[0] == "open"
    # maxicambios domingo 20:00 local (23:00 UTC): fechada
    assert mh.house_status(hours["maxicambios"], utc(2026, 11, 8, 23, 0))[0] == "closed"


def test_maxicambios_saturday_and_sunday_windows_are_distinct():
    maxi = mh.load_market_hours()["maxicambios"]
    # sábado 20:59 local (23:59 UTC): aberta (seg-sáb até 21:00)
    assert mh.house_status(maxi, utc(2026, 11, 7, 23, 59))[0] == "open"
    # sábado 21:00 local: fechada
    assert mh.house_status(maxi, utc(2026, 11, 8, 0, 0))[0] == "closed"
    # domingo 09:45 local (12:45 UTC): pré-abertura de domingo (10:00 menos 30 min)
    assert mh.house_status(maxi, utc(2026, 11, 8, 12, 45))[0] == "pre"


def test_exactly_at_closing_time_is_closed_and_next_session_is_monday_for_chaco_friday():
    # sexta 16:00 local (fechamento de chaco): `closes` é exclusivo; próxima é sábado 07:15 local
    assert mh.house_status(mh.load_market_hours()["chaco"], utc(2026, 11, 6, 19, 0)) == (
        "closed",
        utc(2026, 11, 7, 10, 15),
        utc(2026, 11, 7, 16, 0),
        utc(2026, 11, 7, 9, 45),
    )


def test_bcp_window_is_apuracao_not_publication():
    # BCP: janela de apuração seg-sex 08:30-13:00 local (11:30-16:00 UTC)
    bcp = mh.load_market_hours()["bcp"]
    assert mh.house_status(bcp, utc(2026, 11, 2, 12, 0))[0] == "open"
    assert mh.house_status(bcp, utc(2026, 11, 2, 16, 0)) == (
        "closed",
        utc(2026, 11, 3, 11, 30),
        utc(2026, 11, 3, 16, 0),
        utc(2026, 11, 3, 11, 0),
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


# ---- janelas por dia (schedule) -------------------------------------------------------------------


def _split_house(**fields) -> HouseHours:
    base = {"tz": "UTC", "days": [1, 2, 3, 4, 5], "opens": "08:00", "closes": "17:00"}
    return HouseHours(**{**base, **fields})


def test_schedule_parses_extra_windows_and_procedure_fields():
    text = json.dumps(
        {
            "x": {
                "tz": "UTC",
                "days": [1],
                "opens": "08:00",
                "closes": "17:00",
                "schedule": [{"days": [6], "opens": "09:00", "closes": "12:00"}],
                "verified": True,
                "source_url": "https://example.test/",
                "checked_at": "2026-11-04",
            }
        }
    )
    hours = mh.parse_market_hours(text)["x"]
    assert hours.schedule == [ScheduleWindow(days=[6], opens="09:00", closes="12:00")]
    assert hours.verified is True and hours.checked_at == "2026-11-04"
    assert mh.windows_by_day(hours) == {1: (480, 1020), 6: (540, 720)}


def test_schedule_without_procedure_fields_stays_valid():
    hours = mh.parse_market_hours(
        '{"x": {"tz": "UTC", "days": [1], "opens": "08:00", "closes": "09:00",'
        ' "schedule": [{"days": [2], "opens": "08:00", "closes": "10:00"}]}}'
    )["x"]
    assert hours.verified is None and hours.source_url is None


@pytest.mark.parametrize(
    ("schedule", "message"),
    [
        ([{"days": [1], "opens": "08:00", "closes": "09:00"}], "já têm janela"),
        ([{"days": [], "opens": "08:00", "closes": "09:00"}], "days não pode ser vazio"),
        ([{"days": [6], "opens": "10:00", "closes": "09:00"}], "closes deve ser posterior a opens"),
        ([{"days": [6], "opens": "7:30", "closes": "09:00"}], "opens deve estar"),
        (
            [{"days": [6], "opens": "08:00", "closes": "09:00"}, {"days": [6], "opens": "10:00", "closes": "11:00"}],
            "já têm janela",
        ),
        ([{"days": [8], "opens": "08:00", "closes": "09:00"}], "days deve ter dias ISO"),
    ],
)
def test_schedule_rejects_overlaps_and_invalid_windows(schedule, message):
    text = json.dumps({"x": {"tz": "UTC", "days": [1], "opens": "08:00", "closes": "09:00", "schedule": schedule}})
    with pytest.raises(ValueError, match=r"market_hours\[x\]") as exc:
        mh.parse_market_hours(text)
    assert message in str(exc.value)


def test_schedule_window_boundaries_including_saturday_afternoon():
    hours = _split_house(schedule=[ScheduleWindow(days=[6], opens="09:00", closes="13:00")])
    assert mh.house_status(hours, utc(2026, 11, 7, 12, 59))[0] == "open"  # sábado 12:59
    assert mh.house_status(hours, utc(2026, 11, 7, 13, 0))[0] == "closed"  # sábado 13:00 fecha
    assert mh.house_status(hours, utc(2026, 11, 7, 8, 30)) == (
        "pre",
        utc(2026, 11, 7, 9, 0),
        utc(2026, 11, 7, 13, 0),
        utc(2026, 11, 7, 9, 0),
    )
    assert mh.house_status(hours, utc(2026, 11, 7, 8, 29))[0] == "closed"  # sábado 08:29, antes da pré-abertura
    # domingo sem janela: fechada até segunda 08:00
    assert mh.house_status(hours, utc(2026, 11, 8, 12, 0))[0:2] == ("closed", utc(2026, 11, 9, 8, 0))


def test_schedule_windows_do_not_leak_into_each_other():
    hours = _split_house(schedule=[ScheduleWindow(days=[6], opens="09:00", closes="13:00")])
    # sexta 17:30 (fora da janela de seg-sex) → próxima abertura é sábado 09:00, não segunda
    assert mh.house_status(hours, utc(2026, 11, 6, 17, 30))[1] == utc(2026, 11, 7, 9, 0)
    # sábado 13:30 → a janela de sábado já passou; próxima abertura é segunda 08:00
    assert mh.house_status(hours, utc(2026, 11, 7, 13, 30))[1] == utc(2026, 11, 9, 8, 0)


def test_windows_by_day_is_empty_when_house_has_no_days_and_no_schedule():
    assert mh.windows_by_day(HouseHours(tz="UTC", days=[], opens="08:00", closes="09:00")) == {}


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
