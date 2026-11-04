"""Leitura da volatilidade a partir das velas gravadas (usado pela rota `/v1/market/volatility`)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from . import quotes as q
from . import vol
from .service import load_candles, volatility_payload


def volatility_payloads(session: Session, data_mode: str, *, now: datetime | None = None) -> list[dict]:
    """Um estado por instrumento Binance; sem velas, `insufficient_data` (nunca um número inventado).

    Na demonstração o relógio é a última vela semeada: os dados são fixos e não ficam "parados" (stale).
    """
    now = now or datetime.now(tz=UTC)
    out: list[dict] = []
    for _symbol, _label, instrument in q.BINANCE_SYMBOLS:
        c5, c1 = load_candles(session, instrument, data_mode)
        clock = now
        if data_mode == "demo" and c5:
            clock = c5[-1].close_time + timedelta(seconds=1)
        out.append(volatility_payload(vol.snapshot(instrument, c5, c1, now=clock)))
    return out
