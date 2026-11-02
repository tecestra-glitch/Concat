"""Fake adapters, fake clock and quote helpers for the watch tests (no network, no real adapters)."""
from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from fronteira_fx.adapters.base import AdapterInfo, AdapterResult, AdapterStatus, EvidenceDraft, QuoteDraft

D = Decimal
# Monday 2026-11-02 12:00 UTC = 09:00 in Asunción (UTC-3): business hours.
BUSINESS_NOW = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)
# Monday 06:00 UTC = 03:00 Asunción: off hours.
NIGHT_NOW = datetime(2026, 11, 2, 6, 0, tzinfo=UTC)


class FakeClock:
    def __init__(self, start: datetime = BUSINESS_NOW) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> datetime:
        self.now = self.now + timedelta(seconds=seconds)
        return self.now


def quote(
    base: str = "USD",
    quote_: str = "PYG",
    buy: Any = "7290",
    sell: Any = "7350",
    *,
    source_id: str = "fake",
    city: str | None = "CDE",
    branch_id: str | None = None,
    modality: str = "cash",
    channel: str = "physical",
    amount_base: Any = None,
    context: dict[str, Any] | None = None,
) -> QuoteDraft:
    return QuoteDraft(
        source_id=source_id,
        base=base,  # type: ignore[arg-type]
        quote=quote_,  # type: ignore[arg-type]
        buy=D(str(buy)) if buy is not None else None,
        sell=D(str(sell)) if sell is not None else None,
        unit_note=f"{quote_} por 1 {base}",
        modality=modality,  # type: ignore[arg-type]
        kind="indicative",
        channel=channel,  # type: ignore[arg-type]
        city=city,  # type: ignore[arg-type]
        branch_id=branch_id,
        amount_base=D(str(amount_base)) if amount_base is not None else None,
        context=context,
    )


def result(
    *quotes: QuoteDraft,
    status: AdapterStatus = AdapterStatus.OK,
    message: str | None = None,
    source_id: str = "fake",
) -> AdapterResult:
    evidence = EvidenceDraft(
        source_id=source_id, kind="html", url="https://fake.example/", captured_at=BUSINESS_NOW,
        sha256="0" * 64, excerpt="fake", rules=["fake v1"],
    )
    return AdapterResult(status=status, quotes=list(quotes), evidence=evidence, message=message)


def info(source_id: str = "fake", *, method: str = "html", poll_interval_s: int = 300) -> AdapterInfo:
    return AdapterInfo(
        id=source_id, name=source_id.title(), kind="exchange_house", method=method,  # type: ignore[arg-type]
        url=f"https://{source_id}.example/cotizaciones", capabilities=["buy_sell"], limitations=[],
        cities=["CDE"], currencies=["USD", "BRL", "PYG"], poll_interval_s=poll_interval_s,
    )


@dataclass
class FakeAdapter:
    """Scriptable adapter: `results` is consumed one per fetch/parse (the last one repeats)."""

    info: AdapterInfo
    results: list[AdapterResult] = field(default_factory=list)
    fetch_calls: int = 0
    parse_calls: int = 0
    parsed_bodies: list[str] = field(default_factory=list)
    raise_on_fetch: Exception | None = None

    def _next(self) -> AdapterResult:
        if not self.results:
            return AdapterResult(status=AdapterStatus.ERROR, quotes=[], evidence=None, message="no scripted result")
        if len(self.results) > 1:
            return self.results.pop(0)
        return self.results[0]

    async def fetch(self, **params: Any) -> AdapterResult:
        self.fetch_calls += 1
        if self.raise_on_fetch is not None:
            raise self.raise_on_fetch
        return self._next()

    def parse(self, raw: str | bytes, *, captured_at: datetime, url: str, **params: Any) -> AdapterResult:
        self.parse_calls += 1
        self.parsed_bodies.append(raw if isinstance(raw, str) else raw.decode())
        return self._next()


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
def _reset_router_service() -> Iterator[None]:
    from fronteira_fx.watch import router as router_mod

    router_mod.set_service(None)
    yield
    router_mod.set_service(None)
