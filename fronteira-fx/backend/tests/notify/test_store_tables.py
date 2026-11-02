"""B11: the notify module's own tables must not collide with the core schema (`alert_rules`/`alert_events`)."""

from __future__ import annotations

from sqlalchemy import create_engine, inspect
from sqlalchemy.pool import StaticPool

from fronteira_fx.models import Base
from fronteira_fx.notify.store import NotifyBase, create_notify_tables


def test_notify_tables_are_disjoint_from_core_schema():
    assert set(NotifyBase.metadata.tables).isdisjoint(Base.metadata.tables)
    assert set(NotifyBase.metadata.tables) == {"notify_alert_rules", "notify_alert_events"}


def test_core_schema_and_notify_tables_coexist_in_one_database():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    try:
        Base.metadata.create_all(engine)
        create_notify_tables(engine)
        names = set(inspect(engine).get_table_names())
        assert {"alert_rules", "alert_events", "notify_alert_rules", "notify_alert_events"} <= names
        # core `alert_events` keeps its FK to core `alert_rules`; notify rows are standalone
        core_fks = inspect(engine).get_foreign_keys("alert_events")
        assert any(fk["referred_table"] == "alert_rules" for fk in core_fks)
        assert inspect(engine).get_foreign_keys("notify_alert_events") == []
    finally:
        engine.dispose()
