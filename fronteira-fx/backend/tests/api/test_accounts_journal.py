from fastapi.testclient import TestClient

from fronteira_fx.main import create_app
from tests.conftest import make_settings


def test_accounts_crud(client):
    assert client.get("/v1/accounts").json() == []
    r = client.post(
        "/v1/accounts",
        json={
            "institution": "ueno",
            "label": "ueno conta USD",
            "currency": "USD",
            "kind": "bank",
            "location": "digital",
            "balance_free": "1000.50",
        },
    )
    assert r.status_code == 201, r.text
    acc = r.json()
    assert acc["balance_free"] == "1000.5" and acc["balance_reserved"] == "0" and acc["data_mode"] == "real"
    r = client.patch(f"/v1/accounts/{acc['id']}", json={"balance_free": "900", "balance_in_transit": "100.25"})
    assert r.status_code == 200
    assert (
        r.json()["balance_free"] == "900"
        and r.json()["balance_in_transit"] == "100.25"
        and r.json()["label"] == "ueno conta USD"
    )
    assert client.get("/v1/accounts").json()[0]["id"] == acc["id"]
    assert client.patch("/v1/accounts/missing", json={"balance_free": "1"}).status_code == 404
    assert client.post("/v1/accounts", json={"institution": "x", "label": "y", "currency": "EUR"}).status_code == 422


def test_journal(client):
    r = client.post(
        "/v1/journal",
        json={
            "kind": "operation",
            "text": "comprei USD em CDE",
            "amounts": [{"label": "USD", "amount": "200", "currency": "USD"}],
            "account_ids": [],
        },
    )
    assert r.status_code == 201
    assert r.json()["amounts"][0]["amount"] == "200"
    assert len(client.get("/v1/journal").json()) == 1


def test_api_key_protects_writes_and_mcp():
    app = create_app(make_settings(api_key="s3cret"))
    with TestClient(app) as c:
        assert c.get("/v1/accounts").status_code == 200  # reads stay open
        body = {"institution": "ueno", "label": "x", "currency": "USD"}
        assert c.post("/v1/accounts", json=body).status_code == 401
        assert c.post("/v1/accounts", json=body, headers={"X-API-Key": "wrong"}).status_code == 401
        assert c.post("/v1/accounts", json=body, headers={"X-API-Key": "s3cret"}).status_code == 201
        assert c.post("/v1/accounts", json=body, headers={"Authorization": "Bearer s3cret"}).status_code == 201
        assert c.post("/mcp", json={}).status_code == 401
        assert c.post("/mcp", json={}, headers={"X-API-Key": "s3cret"}).status_code != 401


def test_private_reads_need_the_key_except_health_and_cron():
    app = create_app(make_settings(api_key="s3cret", FX_PRIVATE_READS=True))
    with TestClient(app) as c:
        assert c.get("/v1/health").status_code == 200
        for path in ("/v1/accounts", "/v1/memory", "/v1/journal", "/v1/alerts/rules", "/v1/sources", "/v1/quotes"):
            assert c.get(path).status_code == 401, path
            assert c.get(path, headers={"X-API-Key": "wrong"}).status_code == 401, path
            assert c.get(path, headers={"X-API-Key": "s3cret"}).status_code == 200, path
        assert c.post("/v1/internal/collect").status_code == 404  # its own Bearer; no CRON_SECRET here
        assert c.options("/v1/accounts").status_code != 401


def test_private_reads_off_by_default():
    app = create_app(make_settings(api_key="s3cret"))
    with TestClient(app) as c:
        assert c.get("/v1/accounts").status_code == 200
