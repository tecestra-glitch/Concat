from datetime import timedelta

import pytest

from fronteira_fx.services import events as ev
from tests.conftest import NOW


def test_append_replay_and_cursor(db):
    assert ev.latest_cursor(db) == 0
    e1 = ev.append_event(db, "quote.updated", {"n": 1}, data_mode="real", ts=NOW)
    e2 = ev.append_event(db, "quote.updated", {"n": 2}, data_mode="real", ts=NOW)
    ev.append_event(db, "quote.updated", {"n": 3}, data_mode="demo", ts=NOW)  # other mode: invisible
    assert e2.id == e1.id + 1
    assert ev.latest_cursor(db) == e2.id + 1
    replayed = ev.replay(db, after=e1.id, data_mode="real")
    assert [r.payload["n"] for r in replayed] == [2]
    assert ev.to_stream_event(e1)["id"] == str(e1.id)
    assert ev.parse_cursor("12") == 12 and ev.parse_cursor(None) is None and ev.parse_cursor("") is None
    with pytest.raises(ValueError):
        ev.parse_cursor("abc")
    with pytest.raises(ValueError):
        ev.parse_cursor("-1")


def test_cursor_expired_after_prune(db):
    for i in range(10):
        ev.append_event(db, "heartbeat", {"i": i}, data_mode="real", ts=NOW + timedelta(seconds=i))
    deleted = ev.prune(db, max_events=3, max_age_s=86400, now=NOW + timedelta(seconds=10))
    assert deleted == 7
    oldest = ev.oldest_cursor(db)
    assert oldest == 8
    ev.check_cursor(db, 7)  # cursor just before the oldest retained event is still valid
    ev.check_cursor(db, 9)
    with pytest.raises(ev.CursorExpired) as exc:
        ev.check_cursor(db, 3)
    assert exc.value.oldest == 8 and exc.value.cursor == 3
    with pytest.raises(ev.CursorExpired):
        ev.check_cursor(db, 0)


def test_prune_by_age(db):
    ev.append_event(db, "x", {}, data_mode="real", ts=NOW - timedelta(days=2))
    ev.append_event(db, "x", {}, data_mode="real", ts=NOW)
    assert ev.prune(db, max_events=100, max_age_s=86400, now=NOW) == 1
    assert ev.oldest_cursor(db) == 2
    ev.check_cursor(db, 1)  # no gap between cursor 1 and oldest 2
