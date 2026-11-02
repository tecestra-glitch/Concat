"""Cycles, watch, alerts, rag and memory endpoints."""

from decimal import Decimal

from fronteira_fx.models import Account, AlertRule, Change, Source, WatchState
from tests.conftest import NOW, seed_market

D = Decimal


def test_cycles_from_parked_balances(client, db):
    seed_market(db)
    db.add(
        Account(
            institution="nubank",
            label="Nubank BRL",
            currency="BRL",
            kind="bank",
            location="digital",
            balance_free=D("5000"),
            data_mode="real",
        )
    )
    db.add(
        Account(
            institution="ueno",
            label="ueno PYG",
            currency="PYG",
            kind="bank",
            location="digital",
            balance_free=D("0"),
            data_mode="real",
        )
    )
    db.add(
        Account(
            institution="carteira",
            label="USD em CDE",
            currency="USD",
            kind="cash",
            location="CDE",
            balance_free=D("200"),
            data_mode="real",
        )
    )
    db.commit()
    r = client.get("/v1/opportunities/cycles", params={"max_len": 4})
    assert r.status_code == 200, r.text
    cycles = r.json()
    assert cycles, "expected cycles from BRL@nubank and USD@cash:CDE"
    starts = {c["start"] for c in cycles}
    assert "BRL@nubank" in starts and "USD@cash:CDE" in starts
    c0 = cycles[0]
    assert c0["path"][0] == c0["start"] == c0["path"][-1]
    assert isinstance(c0["amountIn"], float) and isinstance(c0["roi"], float)
    assert c0["edges"][0]["from"] == c0["path"][0] and c0["edges"][-1]["to"] == c0["start"]
    rois = [c["roi"] for c in cycles]
    assert rois == sorted(rois, reverse=True)
    only_brl = client.get("/v1/opportunities/cycles", params={"start": "BRL@nubank", "min_roi": "-1"}).json()
    assert only_brl and all(c["start"] == "BRL@nubank" for c in only_brl)
    assert all(len(c["edges"]) <= 2 for c in client.get("/v1/opportunities/cycles", params={"max_len": 2}).json())
    assert client.get("/v1/opportunities/cycles", params={"max_len": 9}).status_code == 422


def test_watch_endpoints(client, db):
    seed_market(db)
    assert (
        client.get("/v1/watch/sources").json() == []
    )  # no watch state until the collector (or a manual tweak) creates it
    r = client.post("/v1/watch/sources/chaco", json={"interval_s": 120, "enabled": True})
    assert r.status_code == 200, r.text
    st = r.json()
    assert st["source_id"] == "chaco" and st["interval_s"] == 120 and st["enabled"] is True
    assert (
        st["min_interval_s"] == 60 and st["max_interval_s"] == 900 and st["status"] == "ok" and st["changes_24h"] == 0
    )
    assert client.post("/v1/watch/sources/chaco", json={"interval_s": 30}).json()["interval_s"] == 60  # clamped to min
    assert client.post("/v1/watch/sources/chaco", json={"enabled": False}).json()["enabled"] is False
    assert client.post("/v1/watch/sources/nope", json={"enabled": False}).status_code == 404
    assert [s["source_id"] for s in client.get("/v1/watch/sources").json()] == ["chaco"]
    # no adapter registered in tests => 404 on trigger
    assert client.post("/v1/watch/run/chaco").status_code == 404
    db.add(
        Change(
            source_id="chaco",
            ts=NOW,
            kind="quote_change",
            summary="USD/PYG CDE venda 7350 → 7360",
            before={"sell": "7350"},
            after={"sell": "7360"},
            data_mode="real",
        )
    )
    db.add(Change(source_id="wu", ts=NOW, kind="status_change", summary="wu: ok → blocked", data_mode="real"))
    db.add(Change(source_id="wu", ts=NOW, kind="status_change", summary="demo", data_mode="demo"))
    db.commit()
    assert len(client.get("/v1/watch/changes").json()) == 2
    assert [c["kind"] for c in client.get("/v1/watch/changes", params={"source": "chaco"}).json()] == ["quote_change"]
    assert len(client.get("/v1/watch/changes", params={"kind": "status_change"}).json()) == 1
    assert client.get("/v1/watch/changes", params={"from": "2030-01-01T00:00:00Z"}).json() == []


def test_alert_rules_crud_events_and_test_delivery(client, db):
    r = client.post(
        "/v1/alerts/rules",
        json={
            "name": "ciclo > 0,2 %",
            "kind": "cycle_roi",
            "threshold": "0.002",
            "params": {"capital": "5000"},
            "channel": "ui",
            "cooldown_s": 600,
        },
    )
    assert r.status_code == 201, r.text
    rule = r.json()
    assert rule["threshold"] == "0.002" and rule["enabled"] is True and rule["channel"] == "ui"
    assert client.get("/v1/alerts/rules").json()[0]["id"] == rule["id"]
    r = client.patch(f"/v1/alerts/rules/{rule['id']}", json={"enabled": False, "cooldown_s": 60})
    assert r.json()["enabled"] is False and r.json()["cooldown_s"] == 60
    t = client.post(f"/v1/alerts/test/{rule['id']}")
    assert t.status_code == 200, t.text
    assert t.json()["delivered"] is True and t.json()["payload"] == {"test": True} and "[teste]" in t.json()["message"]
    events = client.get("/v1/alerts/events", params={"rule": rule["id"]}).json()
    assert len(events) == 1 and events[0]["channel"] == "ui"
    # webhook to an unreachable target records the error instead of failing the request
    wh = client.post(
        "/v1/alerts/rules",
        json={"name": "wh", "kind": "source_down", "channel": "webhook", "target": "http://127.0.0.1:9/hook"},
    ).json()
    t2 = client.post(f"/v1/alerts/test/{wh['id']}").json()
    assert t2["delivered"] is False and t2["error"]
    tg = client.post(
        "/v1/alerts/rules", json={"name": "tg", "kind": "source_down", "channel": "telegram", "target": "1"}
    ).json()
    assert "TELEGRAM_BOT_TOKEN" in client.post(f"/v1/alerts/test/{tg['id']}").json()["error"]
    assert client.delete(f"/v1/alerts/rules/{rule['id']}").status_code == 204
    assert client.delete(f"/v1/alerts/rules/{rule['id']}").status_code == 404
    assert client.post("/v1/alerts/rules", json={"name": "x", "kind": "bogus"}).status_code == 422


def test_rag_documents_and_search(client):
    r = client.post(
        "/v1/rag/documents",
        json={
            "title": "ueno – tarifas do cartão",
            "source": "ueno docs",
            "tags": ["ueno", "cartao"],
            "text": "Compras internacionais no cartão de débito ueno: spread de 3% sobre a cotação do dia.\n\n"
            "Saques em ATM no exterior: tarifa fixa de USD 5. Horário de atendimento: 8h às 18h.",
            "metadata": {"url": "https://ueno.com.py/tarifas"},
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["chunks"] >= 1
    client.post(
        "/v1/rag/documents",
        json={"title": "Chaco horários", "text": "A filial CDE Centro abre das 7h30 às 17h.", "tags": ["chaco"]},
    )
    docs = client.get("/v1/rag/documents").json()
    assert len(docs) == 2 and {d["title"] for d in docs} == {"ueno – tarifas do cartão", "Chaco horários"}
    hits = client.get("/v1/rag/search", params={"q": "spread cartão débito", "k": 3}).json()
    assert hits and hits[0]["title"] == "ueno – tarifas do cartão" and hits[0]["score"] > 0
    assert (
        "spread" in hits[0]["snippet"].lower()
        and hits[0]["tags"] == ["ueno", "cartao"]
        and hits[0]["source"] == "ueno docs"
    )
    assert client.get("/v1/rag/search", params={"q": "horário", "tag": "chaco"}).json()[0]["title"] == "Chaco horários"
    assert client.get("/v1/rag/search", params={"q": "zzzz nada"}).json() == []


def test_memory_crud(client):
    r = client.post(
        "/v1/memory",
        json={
            "kind": "decision",
            "text": "Preferir ueno para receber WU",
            "tags": ["ueno", "wu"],
            "ttl_days": 30,
            "source": "agent",
        },
    )
    assert r.status_code == 201, r.text
    mem = r.json()
    assert mem["expires_at"] and mem["source"] == "agent" and mem["tags"] == ["ueno", "wu"]
    client.post("/v1/memory", json={"kind": "fact", "text": "Nomad cobra spread maior no fim de semana"})
    assert len(client.get("/v1/memory").json()) == 2
    assert [m["kind"] for m in client.get("/v1/memory", params={"q": "ueno"}).json()] == ["decision"]
    assert [m["id"] for m in client.get("/v1/memory", params={"tag": "wu"}).json()] == [mem["id"]]
    assert len(client.get("/v1/memory", params={"kind": "fact"}).json()) == 1
    assert client.delete(f"/v1/memory/{mem['id']}").status_code == 204
    assert client.delete(f"/v1/memory/{mem['id']}").status_code == 404
    assert len(client.get("/v1/memory").json()) == 1


def test_new_modules_respect_data_mode(client, db):
    db.add(AlertRule(name="demo", kind="source_down", channel="ui", enabled=True, data_mode="demo"))
    db.add(Source(id="demo-x", name="x", kind="bank", method="html", data_mode="demo"))
    db.flush()
    db.add(WatchState(source_id="demo-x", data_mode="demo"))
    db.commit()
    assert client.get("/v1/alerts/rules").json() == []
    assert client.get("/v1/watch/sources").json() == []
    assert client.get("/v1/memory").json() == []
    assert client.get("/v1/rag/documents").json() == []
