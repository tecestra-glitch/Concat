from decimal import Decimal

from tests.conftest import seed_market


def test_quotes_filters_and_string_decimals(client, db):
    seed_market(db)
    all_q = client.get("/v1/quotes").json()
    assert len(all_q) == 10
    q = next(x for x in all_q if x["source_id"] == "chaco" and x["base"] == "USD" and x["city"] == "CDE")
    assert q["buy"] == "7290" and q["sell"] == "7360" and isinstance(q["buy"], str)
    assert q["unit_note"] == "PYG por 1 USD" and q["channel"] == "physical" and q["data_mode"] == "real"
    assert q["branch_id"] == "chaco-cde-centro" and q["context"] is None and q["fees"] == []

    cde = client.get("/v1/quotes", params={"city": "CDE"}).json()
    assert {x["city"] for x in cde} == {"CDE"} and len(cde) == 2
    wu = client.get("/v1/quotes", params={"source": "wu"}).json()
    assert len(wu) == 4 and {x["amount_base"] for x in wu} == {"5000", "10000", "25000", "50000"}
    wu5k = client.get("/v1/quotes", params={"source": "wu", "amount": "5000"}).json()
    assert len(wu5k) == 1 and wu5k[0]["fees"] == [{"label": "tarifa", "amount": "9.9", "currency": "BRL"}]
    assert wu5k[0]["context"]["payment"] == "pix"
    pair = client.get("/v1/quotes", params={"base": "USD", "quote": "BRL"}).json()
    assert [x["source_id"] for x in pair] == ["nomad"]
    assert client.get("/v1/quotes", params={"modality": "account"}).json().__len__() == 2
    assert client.get("/v1/quotes", params={"city": "XXX"}).status_code == 422


def test_request_quote_without_adapter_is_blocked(client, db):
    seed_market(db)
    r = client.post("/v1/quotes/request", json={"source_id": "chaco", "params": {}})
    assert r.status_code == 200
    assert r.json()["status"] == "blocked" and "adaptador" in r.json()["reason"]


def test_history_and_volatility_endpoints(client, db):
    seed_market(db)
    r = client.get(
        "/v1/history",
        params={
            "key": "chaco:CDE:USD/PYG:cash",
            "grid": 300,
            "from": "2026-11-02T11:00:00Z",
            "to": "2026-11-02T12:00:00Z",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["key"] == "chaco:CDE:USD/PYG:cash" and len(body["points"]) == 1
    assert body["points"][0]["mid"] == str((Decimal("7290") + Decimal("7360")) / 2)
    v = client.get("/v1/volatility", params={"key": "chaco:CDE:USD/PYG:cash", "window": "1h"}).json()
    assert v["status"] == "insufficient_data" and v["min_returns"] == 6 and v["grid_s"] == 300
    assert client.get("/v1/volatility", params={"key": "x:y", "window": "7d"}).status_code == 422
