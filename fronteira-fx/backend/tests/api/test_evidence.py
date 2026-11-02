"""MED-08: GET /v1/evidence filters (source, from, q, limit) and GET /v1/evidence/{id}; `q` is a literal substring."""

from __future__ import annotations

from datetime import timedelta

from fronteira_fx.models import Evidence
from tests.conftest import NOW, add_source


def _seed(db):
    add_source(db, "chaco")
    add_source(db, "bcp")
    rows = [
        Evidence(id="ev-1", source_id="chaco", kind="html", captured_at=NOW - timedelta(hours=2), excerpt="USD 7.350 venda", data_mode="real"),
        Evidence(id="ev-2", source_id="chaco", kind="html", captured_at=NOW, excerpt="tarifa 100% isenta", data_mode="real"),
        Evidence(id="ev-3", source_id="bcp", kind="json", captured_at=NOW - timedelta(hours=1), excerpt="ref_media", data_mode="real"),
        Evidence(id="ev-demo", source_id="chaco", kind="html", captured_at=NOW, excerpt="demo 100%", data_mode="demo"),
    ]
    db.add_all(rows)
    db.commit()


def ids(res):
    assert res.status_code == 200, res.text
    return [e["id"] for e in res.json()]


def test_filters_by_source_from_and_limit(client, db):
    _seed(db)
    assert ids(client.get("/v1/evidence")) == ["ev-2", "ev-3", "ev-1"]
    assert ids(client.get("/v1/evidence", params={"source": "chaco"})) == ["ev-2", "ev-1"]
    assert ids(client.get("/v1/evidence", params={"from": (NOW - timedelta(minutes=90)).isoformat()})) == ["ev-2", "ev-3"]
    assert ids(client.get("/v1/evidence", params={"limit": 1})) == ["ev-2"]
    for bad in (0, 501):
        assert client.get("/v1/evidence", params={"limit": bad}).status_code == 422


def test_q_is_a_literal_substring_not_a_like_pattern(client, db):
    _seed(db)
    assert ids(client.get("/v1/evidence", params={"q": "100%"})) == ["ev-2"]
    assert ids(client.get("/v1/evidence", params={"q": "%"})) == ["ev-2"]
    assert ids(client.get("/v1/evidence", params={"q": "ref_"})) == ["ev-3"]
    assert ids(client.get("/v1/evidence", params={"q": "r_f"})) == []
    assert ids(client.get("/v1/evidence", params={"q": "ref%media"})) == []
    assert ids(client.get("/v1/evidence", params={"q": "_"})) == ["ev-3"]


def test_get_by_id_never_crosses_modes(client, db):
    _seed(db)
    res = client.get("/v1/evidence/ev-1")
    assert res.status_code == 200 and res.json()["excerpt"] == "USD 7.350 venda"
    assert client.get("/v1/evidence/nope").status_code == 404
    assert client.get("/v1/evidence/ev-demo").status_code == 404
