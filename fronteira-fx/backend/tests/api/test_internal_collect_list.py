"""POST /v1/internal/collect with a body `{"sources": [...]}`: forced polls of the named sources only.

The no-body round is covered in test_internal_collect.py; these tests cover the list: validation (400, no echo),
the 60 s floor, browser sources, the 30-id limit, and the same authentication rules.
"""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from fronteira_fx.main import create_app
from fronteira_fx.services.collector import Collector
from tests.conftest import NOW, make_settings
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


def test_list_collects_only_the_listed_sources_even_when_not_due():
    clock = Clock(NOW)
    chaco = FakeAdapter("chaco")
    bonanza = FakeAdapter("bonanza")
    with TestClient(build(SECRET, {"chaco": chaco, "bonanza": bonanza}, clock=clock)) as client:
        client.post(URL, headers=bearer(SECRET))  # full round: both polled once, both scheduled later
        assert chaco.calls == 1 and bonanza.calls == 1
        clock.t = NOW + timedelta(seconds=61)  # past the 60 s floor, but not due by schedule (300 s)
        r = client.post(URL, headers=bearer(SECRET), json={"sources": ["chaco"]})
    assert r.status_code == 200
    assert [s["id"] for s in r.json()["sources"]] == ["chaco"]
    assert chaco.calls == 2
    assert bonanza.calls == 1  # not listed, not touched


def test_list_respects_the_60_second_floor():
    clock = Clock(NOW)
    chaco = FakeAdapter("chaco")
    with TestClient(build(SECRET, {"chaco": chaco}, clock=clock)) as client:
        first = client.post(URL, headers=bearer(SECRET), json={"sources": ["chaco"]}).json()
        clock.t = NOW + timedelta(seconds=30)
        second = client.post(URL, headers=bearer(SECRET), json={"sources": ["chaco"]}).json()
    assert [s["id"] for s in first["sources"]] == ["chaco"]
    assert second["sources"] == []
    assert second["skipped"][0]["id"] == "chaco" and "piso de 60 s" in second["skipped"][0]["reason"]
    assert chaco.calls == 1


def test_unknown_id_is_400_and_never_echoes_the_value():
    chaco = FakeAdapter("chaco")
    with TestClient(build(SECRET, {"chaco": chaco})) as client:
        r = client.post(URL, headers=bearer(SECRET), json={"sources": ["chaco", "fonte-inventada-xyz"]})
    assert r.status_code == 400
    assert "fonte-inventada-xyz" not in r.text
    assert chaco.calls == 0  # validated before anything is polled


def test_more_than_30_ids_is_400_and_30_is_fine():
    chaco = FakeAdapter("chaco")
    with TestClient(build(SECRET, {"chaco": chaco})) as client:
        too_many = client.post(URL, headers=bearer(SECRET), json={"sources": ["chaco"] * 31})
        ok = client.post(URL, headers=bearer(SECRET), json={"sources": ["chaco"] * 30})
    assert too_many.status_code == 400
    assert ok.status_code == 200 and [s["id"] for s in ok.json()["sources"]] == ["chaco"]  # duplicates collapse


def test_browser_source_in_the_list_is_skipped_without_a_browser():
    chaco = FakeAdapter("chaco")
    wu = FakeAdapter("wu", method="browser")
    with TestClient(build(SECRET, {"chaco": chaco, "wu": wu})) as client:
        body = client.post(URL, headers=bearer(SECRET), json={"sources": ["wu", "chaco"]}).json()
    assert [s["id"] for s in body["sources"]] == ["chaco"]
    assert body["skipped"][0]["id"] == "wu" and "navegador" in body["skipped"][0]["reason"]
    assert wu.calls == 0


@pytest.mark.parametrize("cron_secret", [None, ""])
def test_list_without_cron_secret_is_404(cron_secret):
    chaco = FakeAdapter("chaco")
    with TestClient(build(cron_secret, {"chaco": chaco})) as client:
        r = client.post(URL, headers=bearer("qualquer"), json={"sources": ["chaco"]})
    assert r.status_code == 404 and chaco.calls == 0


def test_list_with_wrong_secret_is_401():
    chaco = FakeAdapter("chaco")
    with TestClient(build(SECRET, {"chaco": chaco})) as client:
        r = client.post(URL, headers=bearer("errado"), json={"sources": ["chaco"]})
    assert r.status_code == 401 and chaco.calls == 0 and SECRET not in r.text


def test_empty_object_body_is_the_normal_round():
    chaco = FakeAdapter("chaco")
    with TestClient(build(SECRET, {"chaco": chaco})) as client:
        body = client.post(URL, headers=bearer(SECRET), json={}).json()
    assert [s["id"] for s in body["sources"]] == ["chaco"]
