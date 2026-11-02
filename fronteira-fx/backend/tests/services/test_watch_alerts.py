from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select

from fronteira_fx.adapters.base import AdapterStatus
from fronteira_fx.models import AlertEvent, AlertRule, Change, Source, WatchState
from fronteira_fx.services import watch as watch_svc
from fronteira_fx.services.collector import Collector
from tests.conftest import NOW, make_settings
from tests.services.test_collector import Clock, FakeAdapter

D = Decimal


def test_after_run_adapts_interval():
    ws = WatchState(source_id="x", enabled=True, interval_s=300, min_interval_s=60, max_interval_s=900, status="ok")
    watch_svc.after_run(ws, now=NOW, ok=True, changed=True, status="ok", content_hash="a")
    assert ws.interval_s == 150 and ws.last_change_at == NOW and ws.next_run_at == NOW + timedelta(seconds=150)
    watch_svc.after_run(ws, now=NOW, ok=True, changed=True, status="ok", content_hash="b")
    watch_svc.after_run(ws, now=NOW, ok=True, changed=True, status="ok", content_hash="c")
    assert ws.interval_s == 60  # floor
    for _ in range(8):
        watch_svc.after_run(ws, now=NOW, ok=True, changed=False, status="ok", content_hash="c")
    assert ws.interval_s == 900 and ws.errors_in_row == 0  # ceiling
    watch_svc.after_run(ws, now=NOW, ok=False, changed=False, status="blocked", content_hash=None, backoff_max_s=3600)
    assert ws.errors_in_row == 1 and ws.interval_s == 1800 and ws.status == "blocked" and ws.content_hash == "c"
    watch_svc.after_run(ws, now=NOW, ok=False, changed=False, status="blocked", content_hash=None, backoff_max_s=3600)
    assert ws.interval_s == 3600


async def test_collector_records_changes_and_fires_ui_alert(session_factory):
    clock = Clock()
    adapter = FakeAdapter("chaco")
    settings = make_settings()
    collector = Collector(session_factory, settings, adapters={"chaco": adapter}, now_fn=clock)
    with session_factory() as s:
        s.add(
            AlertRule(
                name="movimento USD/PYG",
                kind="quote_move",
                threshold=D("0.001"),
                params={"pair": "USD/PYG"},
                channel="ui",
                cooldown_s=0,
                enabled=True,
                data_mode="real",
            )
        )
        s.add(
            AlertRule(name="fonte caiu", kind="source_down", channel="ui", cooldown_s=0, enabled=True, data_mode="real")
        )
        s.add(AlertRule(name="demo rule invisible", kind="source_down", channel="ui", enabled=True, data_mode="demo"))
        s.commit()

    first = await collector.run_once()
    assert [c.kind for c in first[0].changes] == ["quote_change", "status_change"] or {
        c.kind for c in first[0].changes
    } >= {"quote_change"}
    assert all("nova cotação" in c.summary for c in first[0].changes if c.kind == "quote_change")

    # second capture with a different page (new sha) and a moved price => quote_change with before/after
    adapter.sha = "def"
    adapter.quotes = [q for q in adapter._quotes()]
    adapter.quotes[0].sell = D("7360")
    clock.t = NOW + timedelta(seconds=400)
    second = await collector.run_once()
    out = second[0]
    assert not out.skipped
    qc = [c for c in out.changes if c.kind == "quote_change"]
    assert len(qc) == 1 and "venda 7350 → 7360" in qc[0].summary
    assert qc[0].before["sell"] == "7350" and qc[0].after["sell"] == "7360"
    assert out.alert_event_ids, "quote_move rule should fire (0.136% >= 0.1%)"
    with session_factory() as s:
        ws = s.get(WatchState, "chaco")
        assert ws.content_hash == "def" and ws.last_change_at == clock.t and ws.interval_s < 300
        assert s.get(Source, "chaco").next_poll_at == ws.next_run_at
        events = list(s.scalars(select(AlertEvent)))
        assert len(events) == 1 and events[0].delivered is True and events[0].channel == "ui"
        assert "Movimento" in events[0].message
        kinds = {c.kind for c in s.scalars(select(Change))}
        assert "quote_change" in kinds and "status_change" in kinds
        assert len(watch_svc.list_states(s, data_mode="real", now=clock.t)) == 1
        assert watch_svc.list_states(s, data_mode="real", now=clock.t)[0].changes_24h >= 2

    # source goes down => source_down fires once, status_change recorded
    adapter.status = AdapterStatus.BLOCKED
    clock.t = clock.t + timedelta(seconds=1000)
    third = await collector.run_once()
    assert third[0].health == "blocked" and any(c.kind == "status_change" for c in third[0].changes)
    with session_factory() as s:
        msgs = [e.message for e in s.scalars(select(AlertEvent))]
        assert any("indisponível" in m for m in msgs)
        ws = s.get(WatchState, "chaco")
        assert ws.errors_in_row == 1 and ws.status == "blocked"

    # poll_now returns the first change (or None when nothing changed)
    adapter.status = AdapterStatus.OK
    clock.t = clock.t + timedelta(seconds=5000)
    change = await collector.poll_now("chaco")
    assert change is not None and change.kind == "status_change"
    assert await collector.poll_now("unknown") is None
    clock.t = clock.t + timedelta(seconds=5000)
    assert await collector.poll_now("chaco") is None  # same sha, no changes


def test_detect_quote_changes_matches_contexts(db):
    from fronteira_fx.services.quotes import store_quote_draft
    from tests.conftest import add_source, draft

    add_source(db, "chaco", cities=["CDE"], branches=[("chaco-cde", "CDE")])
    a = store_quote_draft(
        db,
        draft("chaco", "USD", "PYG", "7290", "7360", city="CDE", branch_id="chaco-cde"),
        evidence_id=None,
        data_mode="real",
        captured_at=NOW,
    )
    b = store_quote_draft(
        db,
        draft("chaco", "USD", "PYG", "7290", "7380", city="CDE", branch_id="chaco-cde"),
        evidence_id=None,
        data_mode="real",
        captured_at=NOW + timedelta(minutes=5),
    )
    c = store_quote_draft(
        db,
        draft("chaco", "BRL", "PYG", "1360", "1384", city="CDE", branch_id="chaco-cde"),
        evidence_id=None,
        data_mode="real",
        captured_at=NOW + timedelta(minutes=5),
    )
    changes = watch_svc.detect_quote_changes([a], [b, c])
    assert len(changes) == 2
    summary, before, after = changes[0]
    assert summary == "USD/PYG CDE venda 7360 → 7380" and before["sell"] == "7360" and after["quote_id"] == b.id
    assert "nova cotação" in changes[1][0]
    assert watch_svc.detect_quote_changes([b], [b]) == []
