"""POST /v1/internal/collect: 404 without CRON_SECRET, 401 on a wrong secret, 200 with the right one."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from fronteira_fx.main import create_app
from fronteira_fx.services.collector import Collector
from tests.conftest import NOW, draft, make_settings
from tests.fakes import Clock, FakeAdapter

URL = "/v1/internal/collect"
SECRET = "segredo-de-teste-nao-usar"  # fake value; real secrets never go in tests


def build(cron_secret, adapters, clock=None):
    settings = make_settings(cron_secret=cron_secret)
    app = create_app(settings)
    app.state.collector = Collector(app.state.session_factory, settings, adapters=adapters, now_fn=clock or Clock())
    return app


def bearer(secret):
    return {"Authorization": f"Bearer {secret}"}


@pytest.mark.parametrize("cron_secret", [None, "", "   "])
def test_without_cron_secret_the_route_does_not_exist(cron_secret):
    adapter = FakeAdapter("chaco")
    with TestClient(build(cron_secret, {"chaco": adapter})) as client:
        r = client.post(URL, headers=bearer("qualquer"))
    assert r.status_code == 404
    assert r.json() == {"detail": "Not Found"}
    assert adapter.calls == 0


@pytest.mark.parametrize(
    "headers",
    [{}, {"Authorization": "Bearer errado"}, {"Authorization": f"Basic {SECRET}"}, {"Authorization": SECRET}],
)
def test_wrong_or_missing_secret_is_401(headers):
    adapter = FakeAdapter("chaco")
    with TestClient(build(SECRET, {"chaco": adapter})) as client:
        r = client.post(URL, headers=headers)
    assert r.status_code == 401
    assert SECRET not in r.text
    assert adapter.calls == 0


def test_right_secret_runs_the_round_and_skips_browser_sources():
    chaco = FakeAdapter("chaco")
    wu = FakeAdapter("wu", method="browser")
    with TestClient(build(SECRET, {"chaco": chaco, "wu": wu})) as client:
        r = client.post(URL, headers=bearer(SECRET))
    assert r.status_code == 200
    body = r.json()
    assert body["data_mode"] == "real" and body["budget_exhausted"] is False and body["budget_s"] == 45
    assert isinstance(body["duration_ms"], int) and body["duration_ms"] >= 0
    assert [(s["id"], s["status"], s["changed"], s["quotes_stored"]) for s in body["sources"]] == [
        ("chaco", "ok", False, 1)
    ]
    assert [s["id"] for s in body["skipped"]] == ["wu"] and "navegador" in body["skipped"][0]["reason"]
    assert chaco.calls == 1 and wu.calls == 0
    assert SECRET not in r.text  # the response never echoes the secret, headers or provider bodies


def test_second_call_respects_the_schedule():
    chaco = FakeAdapter("chaco")
    with TestClient(build(SECRET, {"chaco": chaco})) as client:
        client.post(URL, headers=bearer(SECRET))
        body = client.post(URL, headers=bearer(SECRET)).json()
    assert body["sources"] == []
    assert body["skipped"][0]["id"] == "chaco" and body["skipped"][0]["reason"].startswith("próxima sondagem")
    assert chaco.calls == 1


def test_changed_is_true_when_a_quote_moves():
    clock = Clock(NOW)
    chaco = FakeAdapter(
        "chaco", quotes=[draft("chaco", "USD", "PYG", "7300", "7350", city="CDE", branch_id="chaco-cde")]
    )
    with TestClient(build(SECRET, {"chaco": chaco}, clock=clock)) as client:
        client.post(URL, headers=bearer(SECRET))
        chaco.quotes = [draft("chaco", "USD", "PYG", "7310", "7350", city="CDE", branch_id="chaco-cde")]
        chaco.sha = "def"  # a page with new prices has a new hash, so the capture is new
        clock.t = NOW + timedelta(days=1)  # due again
        body = client.post(URL, headers=bearer(SECRET)).json()
    assert body["sources"][0]["id"] == "chaco"
    assert body["sources"][0]["changed"] is True
