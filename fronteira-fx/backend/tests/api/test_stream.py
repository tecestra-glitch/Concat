import json

from fronteira_fx.services import events as ev
from tests.conftest import NOW, make_settings, seed_market


def parse_sse(text: str) -> list[dict]:
    events = []
    for block in text.strip().split("\n\n"):
        item: dict = {}
        for line in block.splitlines():
            if line.startswith("id:"):
                item["id"] = line[3:].strip()
            elif line.startswith("data:"):
                item["data"] = json.loads(line[5:].strip())
            elif line.startswith(":"):
                item.setdefault("comments", []).append(line[1:].strip())
        if item:
            events.append(item)
    return events


def test_snapshot_returns_cursor_and_state(client, db):
    seed_market(db)
    for i in range(3):
        ev.append_event(db, "quote.updated", {"i": i}, data_mode="real", ts=NOW)
    db.commit()
    r = client.get("/v1/snapshot")
    assert r.status_code == 200
    body = r.json()
    assert body["cursor"] == "3" and body["data_mode"] == "real"
    assert len(body["quotes"]) == 10 and len(body["sources"]) == 5 and len(body["opportunities"]) > 0
    assert body["server_time"]


def test_stream_replays_from_cursor_and_header(client, db):
    for i in range(5):
        ev.append_event(db, "quote.updated", {"i": i}, data_mode="real", ts=NOW)
    ev.append_event(db, "quote.updated", {"demo": True}, data_mode="demo", ts=NOW)
    db.commit()
    with client.stream("GET", "/v1/stream", params={"cursor": "2"}) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        text = "".join(r.iter_text())
    events = [e for e in parse_sse(text) if "data" in e]
    replayed = [e for e in events if e["data"]["type"] == "quote.updated"]
    assert [e["data"]["payload"]["i"] for e in replayed] == [2, 3, 4]
    assert all(e["id"] == e["data"]["id"] for e in events)  # id: on every event
    heartbeats = [e for e in events if e["data"]["type"] == "heartbeat"]
    assert heartbeats and heartbeats[-1]["id"] == "5"  # bounded connection emits heartbeats, then closes
    assert "max duration reached" in text

    with client.stream("GET", "/v1/stream", headers={"Last-Event-ID": "4"}) as r:
        text = "".join(r.iter_text())
    replayed = [e for e in parse_sse(text) if "data" in e and e["data"]["type"] == "quote.updated"]
    assert [e["data"]["payload"]["i"] for e in replayed] == [4]


def test_stream_410_when_cursor_expired_and_400_when_invalid(client, db):
    for i in range(10):
        ev.append_event(db, "quote.updated", {"i": i}, data_mode="real", ts=NOW)
    ev.prune(db, max_events=3, max_age_s=86400, now=NOW)
    db.commit()
    r = client.get("/v1/stream", params={"cursor": "2"})
    assert r.status_code == 410
    assert r.json()["detail"]["error"] == "cursor_expired" and r.json()["detail"]["oldest"] == 8
    assert client.get("/v1/stream", headers={"Last-Event-ID": "1"}).status_code == 410
    assert client.get("/v1/stream", params={"cursor": "abc"}).status_code == 400
    with client.stream("GET", "/v1/stream", params={"cursor": "7"}) as ok:
        assert ok.status_code == 200
        ok.close()


def test_stream_is_refused_on_serverless_and_snapshot_still_serves(db):
    """Vercel: nenhum laço de stream. A rota responde 404 antes de qualquer consulta; o cliente usa o snapshot."""
    from fastapi.testclient import TestClient

    from fronteira_fx.main import create_app

    app = create_app(make_settings(serverless=True), mount_mcp_server=False)
    with TestClient(app) as c:
        resp = c.get("/v1/stream")
        assert resp.status_code == 404 and "snapshot" in resp.json()["detail"]
        assert c.get("/v1/snapshot").status_code == 200
