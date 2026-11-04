"""Schemas Pydantic do pregão: velas, resumo da sessão e horários das casas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from fronteira_fx.schemas import ApiModel, DataMode, DecStr

Timeframe = Literal["15m", "1h", "4h", "1d"]
TF_SECONDS: dict[str, int] = {"15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}
SessionStatus = Literal["open", "closed", "pre", "unknown"]
Channel = Literal["physical", "digital"]
HouseCity = Literal["CDE", "ASU", "PJC"]


class Candle(ApiModel):
    t: datetime
    o: DecStr
    h: DecStr
    l: DecStr  # noqa: E741
    c: DecStr
    n: int = Field(ge=1)
    spread_avg: DecStr | None = None
    buy_c: DecStr | None = None
    sell_c: DecStr | None = None
    data_mode: DataMode


class CandleSeries(ApiModel):
    key: str
    tf: Timeframe
    candles: list[Candle]
    data_mode: DataMode


class SessionStats(ApiModel):
    key: str
    day_start: datetime
    open: DecStr | None = None
    high: DecStr | None = None
    low: DecStr | None = None
    last: DecStr | None = None
    last_at: datetime | None = None
    change_abs: DecStr | None = None
    change_pct: DecStr | None = None
    n_quotes: int = 0
    spread_avg: DecStr | None = None
    houses: int = 0
    data_mode: DataMode


class ScheduleWindow(ApiModel):
    """Janela extra de um conjunto de dias (ex.: sábado mais curto). Os dias não podem repetir `HouseHours.days`."""

    days: list[int]
    opens: str
    closes: str


class HouseHours(ApiModel):
    name: str | None = None
    city: HouseCity | None = None
    channel: Channel = "physical"
    tz: str
    days: list[int]
    opens: str
    closes: str
    # Opcionais: janelas de outros dias, e procedência (`source_url`, `checked_at` AAAA-MM-DD, `verified`).
    schedule: list[ScheduleWindow] | None = None
    verified: bool | None = None
    source_url: str | None = None
    checked_at: str | None = None


class HouseSession(ApiModel):
    source_id: str
    name: str
    city: HouseCity | None = None
    tz: str | None = None
    channel: Channel | None = None
    reference: bool = False
    status: SessionStatus
    opens_at: datetime | None = None
    closes_at: datetime | None = None
    next_change_at: datetime | None = None
    data_mode: DataMode
