"""Dados de demonstração do módulo `market` (data_mode = demo). Sem rede e sem manchetes de veículos reais.

Tudo é gerado por uma semente fixa (`random.Random`), então a forma dos dados é sempre a mesma. As manchetes
são ilustrativas, com fonte `demo` e links em `.invalid`, para não parecerem notícias reais.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from ..config import Settings
from ..db import session_scope
from ..models import MarketCandle, MarketQuote, NewsItem
from . import quotes as q
from . import vol

SEED = 20261104
DEMO_SOURCE = "demo"
DEMO_FEED = "demo-ilustrativo"

DEMO_HEADLINES: tuple[str, ...] = (
    "Demonstração: manchete ilustrativa sobre a decisão da Selic",
    "Demonstração: manchete ilustrativa sobre o dólar fechando em alta",
    "Demonstração: manchete ilustrativa sobre a ata do Copom",
    "Demonstração: manchete ilustrativa sobre o guarani",
    "Demonstração: manchete ilustrativa sobre cripto e volatilidade",
    "Demonstração: manchete ilustrativa sobre câmbio na fronteira",
)
BASE_PRICES: dict[str, Decimal] = {
    "BTC/USDT": Decimal("76000"),
    "ETH/USDT": Decimal("2300"),
    "USDT/BRL": Decimal("5.5"),
}


def _candles(rng: random.Random, start: float, count: int, step: timedelta, end: datetime) -> list[vol.Candle]:
    """Caminhada aleatória com OHLC coerente; a última vela fecha em `end`."""
    out: list[vol.Candle] = []
    price = start
    first_open = end - step * count
    for i in range(count):
        open_p = price
        drift = rng.gauss(0, 0.0015 if step == timedelta(minutes=5) else 0.02)
        close_p = max(open_p * (1 + drift), 1e-9)
        spread = abs(rng.gauss(0, 0.001 if step == timedelta(minutes=5) else 0.01))
        high_p = max(open_p, close_p) * (1 + spread)
        low_p = min(open_p, close_p) * (1 - spread)
        open_time = first_open + step * i
        out.append(
            vol.Candle(
                open_time=open_time,
                close_time=open_time + step - timedelta(milliseconds=1),
                open=Decimal(f"{open_p:.8f}"),
                high=Decimal(f"{high_p:.8f}"),
                low=Decimal(f"{low_p:.8f}"),
                close=Decimal(f"{close_p:.8f}"),
            )
        )
        price = close_p
    return out


def seed_market_demo(session_factory: sessionmaker[Session], settings: Settings, *, now: datetime | None = None) -> int:
    """Semeia notícias, referências e velas de demonstração uma vez. Devolve quantas linhas foram criadas."""
    if settings.data_mode != "demo":
        return 0
    now = now or datetime.now(tz=UTC)
    now = now.replace(second=0, microsecond=0)
    with session_scope(session_factory) as session:
        if session.scalar(select(func.count(NewsItem.id)).where(NewsItem.data_mode == "demo")):
            return 0
        created = 0
        for n, title in enumerate(DEMO_HEADLINES):
            published = now - timedelta(hours=n + 1)
            session.add(
                NewsItem(
                    source=DEMO_SOURCE,
                    feed=DEMO_FEED,
                    title=title,
                    link=f"https://demo.invalid/manchete/{n + 1}",
                    published_at=published,
                    captured_at=now,
                    data_mode="demo",
                )
            )
            created += 1
        refs = [
            ("USD/BRL (BCE via Frankfurter)", "USD/BRL", "fx_reference", "5.4530"),
            ("USD/PYG (guarani, via Frankfurter)", "USD/PYG", "fx_reference", "5958"),
            ("PTAX venda (SGS 1)", "PTAX venda", "bcb_series", "5.4935"),
            ("Taxa Selic meta, % a.a. (SGS 432)", "Selic meta", "bcb_series", "13.75"),
        ]
        for label, instrument, kind, price in refs:
            session.add(
                MarketQuote(
                    instrument=instrument,
                    label=label,
                    kind=kind,
                    source="demo",
                    price=Decimal(price),
                    change_pct=None,
                    observed_at=now,
                    captured_at=now,
                    data_mode="demo",
                )
            )
            created += 1
        rng = random.Random(SEED)
        for _symbol, label, instrument in q.BINANCE_SYMBOLS:
            session.add(
                MarketQuote(
                    instrument=instrument,
                    label=label,
                    kind="crypto",
                    source="demo",
                    price=BASE_PRICES[instrument],
                    change_pct=Decimal("0.42"),
                    observed_at=now,
                    captured_at=now,
                    data_mode="demo",
                )
            )
            created += 1
            for interval, count, step in (
                ("5m", vol.SHORT_5M_PER_DAY + 1, timedelta(minutes=5)),
                ("1d", vol.LONG_DAYS + 1, timedelta(days=1)),
            ):
                for c in _candles(rng, float(BASE_PRICES[instrument]), count, step, now):
                    session.add(
                        MarketCandle(
                            instrument=instrument,
                            interval=interval,
                            open_time=c.open_time,
                            close_time=c.close_time,
                            open=c.open,
                            high=c.high,
                            low=c.low,
                            close=c.close,
                            captured_at=now,
                            data_mode="demo",
                        )
                    )
                    created += 1
        session.flush()
        return created
