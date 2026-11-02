"""Fixtures do notify: store em memória e SQLAlchemy (SQLite em memória), parametrizados."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from fronteira_fx.notify.store import AlertStore, InMemoryAlertStore, SqlAlchemyAlertStore, create_notify_tables


@pytest.fixture(params=["memory", "sql"])
def store(request: pytest.FixtureRequest) -> Iterator[AlertStore]:
    if request.param == "memory":
        yield InMemoryAlertStore()
        return
    engine = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    create_notify_tables(engine)
    yield SqlAlchemyAlertStore(sessionmaker(bind=engine, expire_on_commit=False))
    engine.dispose()
