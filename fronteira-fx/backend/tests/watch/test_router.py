from __future__ import annotations

from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

import fronteira_fx.watch as router_mod
from fronteira_fx.watch.router import get_service, router
from fronteira_fx.watch.scheduler import Scheduler, SchedulerConfig
from fronteira_fx.watch.service import WatchService
from tests.watch.conftest import FakeAdapter, FakeClock, info, quote, result


def build(clock: FakeClock, adapters: dict, *, override: bool = False) -> tuple[TestClient, WatchService, list]:
    events: list = []
    svc = WatchService(adapters=adapters, clock=clock, scheduler=Scheduler(SchedulerConfig(jitter=0.0), clock=clock),
                       emit=lambda t, p: events.append((t, p)))
    app = FastAPI()
    app.include_router(router)
    if override:
        app.dependency_overrides[get_service] = lambda: svc
    else:
        router_mod.set_service(svc)
    return TestClient(app), svc, events


def test_routes_and_operation_ids_match_contract(clock):
    client, _, _ = build(clock, {})
    spec = client.get("/openapi.json").json()
    ops = {(m.upper(), path): op["operationId"] for path, item in spec["paths"].items() for m, op in item.items()}
    assert ops == {
        ("GET", "/v1/watch/sources"): "watch_status",
        ("POST", "/v1/watch/sources/{source_id}"): "watch_update_source",
        ("POST", "/v1/watch/run/{source_id}"): "trigger_poll",
        ("GET", "/v1/watch/changes"): "list_changes",
    }
    params = {p["name"] for p in spec["paths"]["/v1/watch/changes"]["get"]["parameters"]}
    assert {"source", "from", "kind", "limit"} <= params


def test_full_flow_through_http(clock):
    adapter = FakeAdapter(info("fake", method="browser"), results=[
        result(quote(buy="7290", sell="7350")),
        result(quote(buy="7290", sell="7360")),
    ])
    client, svc, events = build(clock, {"fake": adapter})

    r = client.get("/v1/watch/sources")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1 and body[0]["source_id"] == "fake" and body[0]["status"] == "stale"
    assert body[0]["interval_s"] == 300 and body[0]["min_interval_s"] == 60 and body[0]["max_interval_s"] == 900
    assert body[0]["enabled"] is True and body[0]["content_hash"] is None and body[0]["changes_24h"] == 0

    r = client.post("/v1/watch/run/fake")
    assert r.status_code == 200 and r.json() is None  # baseline
    r = client.post("/v1/watch/run/fake")
    assert r.status_code == 200
    change = r.json()
    assert change["kind"] == "quote_change" and change["summary"] == "USD/PYG CDE venda 7350 → 7360"
    assert change["source_id"] == "fake" and change["before"]["sell"] == "7350" and change["after"]["sell"] == "7360"
    assert change["evidence_id"] is None and change["id"]
    datetime.fromisoformat(change["ts"])  # ISO-8601
    assert len(events) == 1 and events[0][0] == "source.change"

    r = client.get("/v1/watch/changes")
    assert [c["id"] for c in r.json()] == [change["id"]]
    assert client.get("/v1/watch/changes", params={"source": "other"}).json() == []
    assert client.get("/v1/watch/changes", params={"kind": "layout_change"}).json() == []
    assert len(client.get("/v1/watch/changes", params={"kind": "quote_change", "source": "fake"}).json()) == 1
    future = datetime(2030, 1, 1, tzinfo=UTC).isoformat()
    assert client.get("/v1/watch/changes", params={"from": future}).json() == []
    assert len(client.get("/v1/watch/changes", params={"from": "2026-11-02T00:00:00Z"}).json()) == 1
    assert client.get("/v1/watch/changes", params={"kind": "bogus"}).status_code == 422

    r = client.get("/v1/watch/sources")
    st = r.json()[0]
    assert st["status"] == "ok" and st["changes_24h"] == 1 and st["interval_s"] == 150 and st["content_hash"]
    assert st["last_change_at"] is not None and st["errors_in_row"] == 0


def test_update_source_and_404s(clock):
    adapter = FakeAdapter(info("fake", method="browser"), results=[result(quote())])
    client, _, _ = build(clock, {"fake": adapter}, override=True)
    r = client.post("/v1/watch/sources/fake", json={"interval_s": 45})
    assert r.status_code == 200
    assert r.json()["interval_s"] == 60 and r.json()["interval_override_s"] == 60  # clamped: never hammer
    r = client.post("/v1/watch/sources/fake", json={"enabled": False})
    assert r.json()["enabled"] is False and r.json()["next_run_at"] is None
    r = client.post("/v1/watch/sources/fake", json={})
    assert r.status_code == 200 and r.json()["enabled"] is False
    assert client.post("/v1/watch/sources/fake", json={"interval_s": 0}).status_code == 422
    assert client.post("/v1/watch/sources/nope", json={"enabled": True}).status_code == 404
    assert client.post("/v1/watch/run/nope").status_code == 404
    r = client.post("/v1/watch/run/fake", params={"force": "true"})
    assert r.status_code == 200 and r.json() is None


def test_default_service_factory_is_lazy_and_overridable():
    router_mod.set_service(None)
    svc = get_service()
    assert isinstance(svc, WatchService) and get_service() is svc
    other = WatchService(adapters={})
    router_mod.set_service(other)
    assert get_service() is other
