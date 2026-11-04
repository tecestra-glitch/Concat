"""Fixtures offline do módulo market: banco SQLite em memória, fixtures de feeds e de JSON reais (recortados)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy.orm import Session, sessionmaker

from fronteira_fx.config import Settings
from fronteira_fx.db import create_schema, make_engine, make_session_factory

FIXTURES = Path(__file__).parent / "fixtures"


def read_fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def market_settings(data_mode: str = "real") -> Settings:
    return Settings(
        _env_file=None,
        database_url="sqlite://",
        auto_create_schema=True,
        data_mode=data_mode,
        seed_demo=False,
        seed_knowledge=False,
        quotes_lookback_s=10 * 365 * 86400,
    )


@pytest.fixture
def market_factory() -> Iterator[sessionmaker[Session]]:
    engine = make_engine("sqlite://")
    create_schema(engine)
    yield make_session_factory(engine)
    engine.dispose()
