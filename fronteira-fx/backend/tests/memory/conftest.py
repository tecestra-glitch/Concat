"""Fixtures da memória: relógio falso e os dois armazenamentos (em memória e SQLite via SQLAlchemy)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from fronteira_fx.memory.service import MemoryService
from fronteira_fx.memory.store import InMemoryStore, MemoryStore, SqlStore, create_memory_tables

T0 = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)


class FakeClock:
    def __init__(self, now: datetime = T0) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta: float) -> None:
        self.now += timedelta(**delta)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture(params=["memory", "sql"])
def store(request: pytest.FixtureRequest) -> MemoryStore:
    if request.param == "memory":
        return InMemoryStore()
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    create_memory_tables(engine)
    return SqlStore(sessionmaker(bind=engine, expire_on_commit=False))


@pytest.fixture
def service(store: MemoryStore, clock: FakeClock) -> MemoryService:
    return MemoryService(store, clock=clock)
