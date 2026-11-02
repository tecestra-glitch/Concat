from decimal import Decimal

from tests.conftest import seed_market

D = Decimal


def test_compare_routes_returns_ranked_opportunities_and_search(client, db):
    seed_market(db)
    body = {
        "capital_brl": "5000",
        "objective": "cycle",
        "valuation_currency": "BRL",
        "channels": ["digital", "physical"],
    }
    r = client.post("/v1/simulations/routes", json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    opps = data["opportunities"]
    assert opps, "expected candidates from the seeded market"
    assert all(o["capital_brl"] == "5000" and o["kind"] == "cycle" for o in opps)
    main = [o for o in opps if o["in_main_ranking"]]
    secondary = [o for o in opps if not o["in_main_ranking"]]
    assert opps == main + secondary  # main first
    rois = [D(o["roi"]) for o in main]
    assert rois == sorted(rois, reverse=True)
    assert all(D(o["net_gain_brl"]) > 0 for o in main)
    for o in opps:
        assert isinstance(o["roi"], str) and o["ranking_reason"]
        assert o["steps"][0]["from"]["currency"] == "BRL" and o["steps"][-1]["to"]["currency"] == "BRL"
        assert o["confidence"] in ("quoted", "estimated", "incomplete")
    tested = data["search"]["amounts_tested"]
    assert {"5000", "10000", "25000", "50000"} <= set(tested) and len(tested) <= 12
    assert tested == sorted(tested, key=D)
    assert "boundaries" in data["search"]
    # same input => same output (determinism; only computed_at differs)
    again = client.post("/v1/simulations/routes", json=body).json()["opportunities"]
    strip = lambda rows: [{k: v for k, v in o.items() if k != "computed_at"} for o in rows]
    assert strip(again) == strip(opps)
    # different amount => different result
    other = client.post("/v1/simulations/routes", json={**body, "capital_brl": "10000"}).json()["opportunities"]
    assert {o["id"] for o in other}.isdisjoint({o["id"] for o in opps})
    assert [o["roi"] for o in other] != [o["roi"] for o in opps]


def test_physical_rule_applied_in_api_ranking(client, db):
    seed_market(db)
    opps = client.post("/v1/simulations/routes", json={"capital_brl": "25000", "objective": "cycle"}).json()[
        "opportunities"
    ]
    phys = [o for o in opps if o["channel"] == "physical"]
    assert phys and all(o["city"] for o in phys)
    best_digital = max(
        (
            D(o["roi"])
            for o in opps
            if o["channel"] == "digital" and D(o["net_gain_brl"]) > 0 and o["confidence"] != "incomplete"
        ),
        default=None,
    )
    for o in phys:
        if best_digital is None:
            assert o["in_main_ranking"] == (D(o["net_gain_brl"]) > 0)
        else:
            assert (
                o["comparable_best_digital_roi"] == str(best_digital).rstrip("0").rstrip(".")
                or D(o["comparable_best_digital_roi"]) == best_digital
            )
            assert o["in_main_ranking"] == (D(o["net_gain_brl"]) > 0 and D(o["roi"]) >= best_digital + D("0.01"))


def test_remittance_objective_and_persist(client, db):
    seed_market(db)
    r = client.post(
        "/v1/simulations/routes",
        json={
            "capital_brl": "10000",
            "objective": "remittance",
            "destination": {"currency": "PYG", "location": "digital"},
            "persist": True,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["simulation_id"]
    assert all(o["kind"] == "remittance_saving" for o in data["opportunities"])
    assert any(D(o["net_gain_brl"]) == 0 for o in data["opportunities"])  # the reference (worst) route
    assert any(D(o["net_gain_brl"]) > 0 for o in data["opportunities"])


def test_opportunities_listing_filters(client, db):
    seed_market(db)
    rows = client.get("/v1/opportunities", params={"capital": "5000"}).json()
    assert rows and {r["capital_brl"] for r in rows} == {"5000"}
    phys = client.get("/v1/opportunities", params={"capital": "5000", "channel": "physical", "city": "CDE"}).json()
    assert all(r["channel"] == "physical" and r["city"] == "CDE" for r in phys)
    assert client.get("/v1/opportunities", params={"kind": "remittance_saving"}).json()


def test_simulate_cycle_explicit_steps(client):
    body = {
        "capital": "5000",
        "valuation_currency": "BRL",
        "steps": [
            {
                "description": "Pix BRL -> WU -> ueno PYG",
                "from": {"currency": "BRL", "modality": "transfer"},
                "to": {"currency": "PYG", "institution": "ueno"},
                "rate": "1380",
                "fees": [{"label": "tarifa", "amount": "0", "currency": "BRL"}],
            },
            {
                "description": "PYG -> BRL em CDE",
                "from": {"currency": "PYG", "location": "CDE", "modality": "cash"},
                "to": {"currency": "BRL", "location": "CDE", "modality": "cash"},
                "rate": "0.000725689",
                "confidence": "estimated",
                "fees": [{"label": "IOF?", "amount": None, "currency": "BRL"}],
            },
        ],
    }
    r = client.post("/v1/simulations/cycle", json=body)
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["confidence"] == "incomplete" and res["pending_costs"]
    assert res["effective_rate"] == str(
        (D("5000") * D("1380") * D("0.000725689") / D("5000")).quantize(D("0.00000001"))
    ).rstrip("0")
    assert res["steps"][1]["from"]["location"] == "CDE"
    bad = {"capital": "1", "steps": [{"description": "x", "from": {"currency": "BRL"}, "to": {"currency": "PYG"}}]}
    assert client.post("/v1/simulations/cycle", json=bad).status_code == 422
