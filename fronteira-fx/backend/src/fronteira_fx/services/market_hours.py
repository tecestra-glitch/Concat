"""Horários de funcionamento das casas e status da sessão (aberta, fechada, pré-abertura, sem horário).

Os horários vêm de `data/market_hours.json` (§0.7) e são interpretados no fuso de cada casa. Janelas de
outros dias vão em `schedule`. Casa sem horário, fuso inválido ou `hours` nulo → `unknown`: nunca se inventa
horário. `house_status` devolve sempre datetimes UTC.
"""

from __future__ import annotations

import json
import re
from collections.abc import Collection
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from importlib import resources
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import ValidationError

from fronteira_fx.schemas import DataMode
from fronteira_fx.schemas_candles import HouseHours, HouseSession, SessionStatus

PRE_OPEN_MIN = 30
StatusTuple = tuple[SessionStatus, datetime | None, datetime | None, datetime | None]

_ALL_DAYS = frozenset(range(1, 8))
_UNKNOWN: StatusTuple = ("unknown", None, None, None)
_HHMM = re.compile(r"[0-9]{2}:[0-9]{2}")

Window = tuple[int, int]  # (abertura, fechamento) em minutos desde 00:00 local


def _read_text() -> str:
    return resources.files("fronteira_fx").joinpath("data/market_hours.json").read_text("utf-8")


def _is_hhmm(value: str) -> bool:
    """`HH:MM` com horas 00–23 (ou `24:00`) e minutos 00–59."""
    if _HHMM.fullmatch(value) is None:
        return False
    hours, minutes = int(value[:2]), int(value[3:])
    return minutes < 60 and (hours < 24 or (hours == 24 and minutes == 0))


def _check_window(source_id: str, where: str, days: list[int], opens: str, closes: str) -> None:
    def fail(message: str) -> ValueError:
        return ValueError(f"market_hours[{source_id}]: {where}{message}")

    if len(set(days)) != len(days) or not set(days) <= _ALL_DAYS:
        raise fail(f"days deve ter dias ISO de 1 a 7, sem repetição: {days}")
    if not _is_hhmm(opens) or minutes_of(opens) >= 1440:
        raise fail(f"opens deve estar entre 00:00 e 23:59 (HH:MM): {opens!r}")
    if not _is_hhmm(closes) or not 1 <= minutes_of(closes) <= 1440:
        raise fail(f"closes deve estar entre 00:01 e 24:00 (HH:MM): {closes!r}")
    if minutes_of(closes) <= minutes_of(opens):
        raise fail("closes deve ser posterior a opens")


def _validate(source_id: str, hours: HouseHours) -> None:
    if source_id.startswith("demo-"):
        raise ValueError(f"market_hours[{source_id}]: chave com prefixo demo- (o arquivo não tem prefixo)")
    _check_window(source_id, "", hours.days, hours.opens, hours.closes)
    covered = set(hours.days)
    for index, window in enumerate(hours.schedule or []):
        where = f"schedule[{index}]: "
        if not window.days:
            raise ValueError(f"market_hours[{source_id}]: {where}days não pode ser vazio")
        _check_window(source_id, where, window.days, window.opens, window.closes)
        overlap = covered & set(window.days)
        if overlap:
            raise ValueError(f"market_hours[{source_id}]: {where}dias {sorted(overlap)} já têm janela")
        covered |= set(window.days)


def parse_market_hours(text: str) -> dict[str, HouseHours]:
    """Interpreta o JSON de horários; qualquer violação vira `ValueError` com o `source_id` na mensagem."""
    raw = json.loads(text)
    if not isinstance(raw, dict):
        raise ValueError("market_hours: o arquivo deve ser um objeto JSON")
    houses: dict[str, HouseHours] = {}
    for source_id, entry in raw.items():
        try:
            hours = HouseHours.model_validate(entry)
        except ValidationError as exc:
            raise ValueError(f"market_hours[{source_id}]: {exc}") from exc
        _validate(source_id, hours)
        houses[source_id] = hours
    return houses


@lru_cache(maxsize=1)
def load_market_hours() -> dict[str, HouseHours]:
    """Horários de `data/market_hours.json`; lido uma vez por processo."""
    return parse_market_hours(_read_text())


def strip_demo_prefix(source_id: str) -> str:
    """`demo-chaco` → `chaco`; as chaves de `market_hours.json` não têm prefixo."""
    return source_id.removeprefix("demo-")


def minutes_of(hhmm: str) -> int:
    """`"07:30"` → 450; `"24:00"` → 1440."""
    return int(hhmm[:2]) * 60 + int(hhmm[3:5])


def is_always_open(hours: HouseHours) -> bool:
    """Sete dias, `00:00`–`24:00`: casa digital sempre aberta (§0.7 passo 2)."""
    return _ALL_DAYS <= set(hours.days) and hours.opens == "00:00" and hours.closes == "24:00"


def local_midnight_utc(day: datetime, tz: ZoneInfo) -> datetime:
    """00:00 do dia civil de `day` (data local) no fuso `tz`, convertido para UTC."""
    return datetime(day.year, day.month, day.day, tzinfo=tz).astimezone(UTC)


def windows_by_day(hours: HouseHours) -> dict[int, Window]:
    """Janela `(abertura, fechamento)` em minutos de cada dia ISO em que a casa abre. Dia ausente = fechado."""
    windows: dict[int, Window] = {day: (minutes_of(hours.opens), minutes_of(hours.closes)) for day in hours.days}
    for extra in hours.schedule or []:
        for day in extra.days:
            windows[day] = (minutes_of(extra.opens), minutes_of(extra.closes))
    return windows


def _window_utc(local_midnight: datetime, window: Window) -> tuple[datetime, datetime]:
    """Abertura e fechamento do dia (meia-noite local, com fuso) em UTC; `24:00` cai no dia seguinte."""
    opens, closes = window
    return (
        (local_midnight + timedelta(minutes=opens)).astimezone(UTC),
        (local_midnight + timedelta(minutes=closes)).astimezone(UTC),
    )


def house_status(hours: HouseHours | None, now: datetime) -> StatusTuple:
    """Status da casa em `now` (§0.7): `(status, opens_at, closes_at, next_change_at)`, todos em UTC."""
    if hours is None:
        return _UNKNOWN
    now = now.replace(tzinfo=UTC) if now.tzinfo is None else now.astimezone(UTC)
    try:
        tz = ZoneInfo(hours.tz)
    except (ZoneInfoNotFoundError, ValueError):
        return _UNKNOWN
    if is_always_open(hours):
        return ("open", None, None, None)

    windows = windows_by_day(hours)
    if not windows:
        return ("closed", None, None, None)
    local = now.astimezone(tz)
    weekday = local.isoweekday()
    minute = local.hour * 60 + local.minute
    today = datetime(local.year, local.month, local.day, tzinfo=tz)
    window = windows.get(weekday)

    if window is not None:
        opens, closes = window
        if opens <= minute < closes:
            opens_at, closes_at = _window_utc(today, window)
            return ("open", opens_at, closes_at, closes_at)
        if opens - PRE_OPEN_MIN <= minute < opens:
            opens_at, closes_at = _window_utc(today, window)
            return ("pre", opens_at, closes_at, opens_at)

    first = 0 if window is not None and minute < window[0] - PRE_OPEN_MIN else 1
    for offset in range(first, first + 8):
        day = today + timedelta(days=offset)
        day_window = windows.get(day.isoweekday())
        if day_window is not None:
            opens_at, closes_at = _window_utc(day, day_window)
            return ("closed", opens_at, closes_at, opens_at - timedelta(minutes=PRE_OPEN_MIN))
    return ("closed", None, None, None)


def house_sessions(
    now: datetime,
    table: dict[str, HouseHours | None],
    mode: DataMode,
    reference_ids: Collection[str] = (),
) -> list[HouseSession]:
    """Uma `HouseSession` por chave de `table`, na ordem das chaves; `name = hours.name or source_id`."""
    sessions: list[HouseSession] = []
    for source_id, hours in table.items():
        status, opens_at, closes_at, next_change_at = house_status(hours, now)
        sessions.append(
            HouseSession(
                source_id=source_id,
                name=(hours.name if hours is not None and hours.name else source_id),
                city=hours.city if hours is not None else None,
                tz=hours.tz if hours is not None else None,
                channel=hours.channel if hours is not None else None,
                reference=source_id in reference_ids,
                status=status,
                opens_at=opens_at,
                closes_at=closes_at,
                next_change_at=next_change_at,
                data_mode=mode,
            )
        )
    return sessions
