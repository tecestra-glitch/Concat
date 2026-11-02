from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import inspect

from fronteira_fx.watch.schemas import Change, WatchStatus
from fronteira_fx.watch.store_sql import SqlWatchStore, WatchBase

NOW = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)


def test_own_tables_and_metadata():
    store = SqlWatchStore.from_url("sqlite://")
    engine = store.session_factory.kw["bind"]
    assert set(inspect(engine).get_table_names()) == {"watch_status", "watch_changes"}
    assert set(WatchBase.metadata.tables) == {"watch_status", "watch_changes"}


def test_status_round_trip_and_snapshot():
    store = SqlWatchStore.from_url("sqlite://")
    assert store.load_status("chaco") is None and store.list_status() == []
    st = WatchStatus(
        source_id="chaco", enabled=True, interval_s=120, min_interval_s=60, max_interval_s=900,
        next_run_at=NOW + timedelta(seconds=120), last_run_at=NOW, last_change_at=None, errors_in_row=2,
        etag='"abc"', last_modified="Mon, 02 Nov 2026 12:00:00 GMT", content_hash="f" * 64, status="degraded",
        last_error="1 branch missing", interval_override_s=120, mode="conditional_get",
    )
    store.save_status(st)
    loaded = store.load_status("chaco")
    assert loaded is not None
    assert loaded.model_dump(exclude={"changes_24h"}) == st.model_dump(exclude={"changes_24h"})
    assert loaded.next_run_at.tzinfo is not None  # SQLite gives naive datetimes back; we restore UTC
    st.enabled = False
    store.save_status(st)
    assert store.load_status("chaco").enabled is False and len(store.list_status()) == 1
    store.save_snapshot("chaco", {"status": "ok", "rows": [[None, "CDE", "USD", "PYG", "cash", "physical", None, "", "7290", "7350"]]})
    assert store.load_snapshot("chaco")["rows"][0][8] == "7290"
    assert store.load_snapshot("nope") is None
    # a snapshot saved before any status creates the row without breaking later status saves
    store.save_snapshot("ueno", {"status": "ok", "rows": []})
    store.save_status(WatchStatus(source_id="ueno", interval_s=300, min_interval_s=60, max_interval_s=900))
    assert store.load_snapshot("ueno") == {"status": "ok", "rows": []}


def test_changes_filters_order_and_count():
    store = SqlWatchStore.from_url("sqlite://")

    def ch(i: int, source: str, kind: str, ts: datetime) -> Change:
        return Change(id=f"id-{i}", source_id=source, ts=ts, kind=kind, summary=f"c{i}",  # type: ignore[arg-type]
                      before={"sell": "1"}, after={"sell": "2"})

    store.save_change(ch(1, "chaco", "quote_change", NOW - timedelta(hours=30)))
    store.save_change(ch(2, "chaco", "quote_change", NOW - timedelta(hours=2)))
    store.save_change(ch(3, "chaco", "status_change", NOW - timedelta(hours=1)))
    store.save_change(ch(4, "ueno", "quote_change", NOW))
    store.save_change(ch(4, "ueno", "quote_change", NOW))  # idempotent on id
    assert [c.id for c in store.list_changes()] == ["id-4", "id-3", "id-2", "id-1"]
    assert [c.id for c in store.list_changes(source_id="chaco")] == ["id-3", "id-2", "id-1"]
    assert [c.id for c in store.list_changes(kind="status_change")] == ["id-3"]
    assert [c.id for c in store.list_changes(since=NOW - timedelta(hours=3))] == ["id-4", "id-3", "id-2"]
    assert [c.id for c in store.list_changes(limit=2)] == ["id-4", "id-3"]
    assert store.count_changes("chaco", since=NOW - timedelta(hours=24)) == 2
    first = store.list_changes(source_id="ueno")[0]
    assert first.before == {"sell": "1"} and first.after == {"sell": "2"} and first.ts == NOW
