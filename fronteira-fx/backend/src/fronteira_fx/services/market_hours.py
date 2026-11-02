"""Horários de funcionamento das casas e status da sessão (aberta, fechada, pré-abertura, sem horário).

A fundação (W0A) entrega `PRE_OPEN_MIN`, `strip_demo_prefix`, `is_always_open` e `house_sessions`;
`load_market_hours` e `house_status` são stubs que a unidade B6 substitui mantendo as assinaturas.
Stubs nunca lançam exceção.
"""

from __future__ import annotations

from collections.abc import Collection
from datetime import datetime

from fronteira_fx.schemas import DataMode
from fronteira_fx.schemas_candles import HouseHours, HouseSession, SessionStatus

PRE_OPEN_MIN = 30
StatusTuple = tuple[SessionStatus, datetime | None, datetime | None, datetime | None]

_ALL_DAYS = frozenset(range(1, 8))


def load_market_hours() -> dict[str, HouseHours]:
    """Stub da fundação: nenhum horário carregado (toda fonte fica `unknown`). B6 lê `data/market_hours.json`."""
    return {}


def strip_demo_prefix(source_id: str) -> str:
    """`demo-chaco` → `chaco`; as chaves de `market_hours.json` não têm prefixo."""
    return source_id.removeprefix("demo-")


def is_always_open(hours: HouseHours) -> bool:
    """Sete dias, `00:00`–`24:00`: casa digital sempre aberta (§0.7 passo 2)."""
    return _ALL_DAYS <= set(hours.days) and hours.opens == "00:00" and hours.closes == "24:00"


def house_status(hours: HouseHours | None, now: datetime) -> StatusTuple:
    """Stub da fundação: `("unknown", None, None, None)`. B6 implementa o algoritmo de §0.7."""
    return ("unknown", None, None, None)


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
