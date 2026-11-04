"""Fase A: dados versionados de deslocamento (`transport.json`) e trilhos (`rails.json`) com loader validado."""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from fronteira_fx.services.logistics import (
    load_rails,
    load_transport,
    parse_rails,
    parse_transport,
)

D = Decimal


def route(**overrides) -> dict:
    base = {
        "id": "cde-asu",
        "from_city": "CDE",
        "to_city": "ASU",
        "mode": "bus",
        "cost": None,
        "minutes": 240,
        "border": False,
        "symmetric": True,
        "source_url": None,
        "checked_at": None,
        "verified": False,
    }
    base.update(overrides)
    return base


def rail(**overrides) -> dict:
    base = {
        "id": "pix-br-bank-revolut-brl",
        "from": "br_bank",
        "to": "revolut",
        "currency": "BRL",
        "to_currency": "BRL",
        "fee_fixed": None,
        "fee_pct": None,
        "iof_pct": None,
        "minutes": 5,
        "min_amount": None,
        "max_amount": None,
        "source_url": None,
        "checked_at": None,
        "verified": False,
    }
    base.update(overrides)
    return base


def test_shipped_transport_file_loads_the_six_cities_and_the_initial_routes():
    routes = load_transport()
    ids = {r.id for r in routes.values()}
    assert {"foz-cde", "cde-asu", "asu-pjc", "pjc-ppo", "cde-enc"} <= ids
    cities = {r.from_city for r in routes.values()} | {r.to_city for r in routes.values()}
    assert {"CDE", "ASU", "PJC", "ENC", "FOZ", "PPO"} <= cities
    assert all(r.cost is None and r.verified is False for r in routes.values())
    assert routes["foz-cde"].border is True
    assert routes["cde-asu"].border is False


def test_shipped_rails_file_has_the_lines_the_engine_needs():
    rails = load_rails()
    assert {"pix-br-bank-revolut-brl", "nomad-revolut-usd", "sipap-py-bank-to-house-pyg"} <= set(rails)
    assert all(r.fee_fixed is None and r.verified is False for r in rails.values())


def test_money_is_a_decimal_string_and_never_a_float():
    raw = route(cost={"amount": "35.50", "currency": "BRL"})
    parsed = parse_transport(f"[{json.dumps(raw)}]")
    assert parsed["cde-asu"].cost is not None
    assert parsed["cde-asu"].cost.amount == D("35.50")
    assert parsed["cde-asu"].cost.currency == "BRL"


def test_float_money_is_rejected_with_the_line_id():
    raw = route(cost={"amount": 35.5, "currency": "BRL"})
    with pytest.raises(ValueError, match="transport\\[cde-asu\\]"):
        parse_transport(json.dumps([raw]))


def test_unknown_city_is_rejected_with_the_line_id():
    raw = route(from_city="XYZ")
    with pytest.raises(ValueError, match="transport\\[cde-asu\\]"):
        parse_transport(json.dumps([raw]))


def test_duplicate_ids_are_rejected():
    with pytest.raises(ValueError, match="duplicad"):
        parse_transport(json.dumps([route(), route()]))


def test_verified_route_needs_a_source_and_a_date():
    raw = route(verified=True, cost={"amount": "35", "currency": "BRL"})
    with pytest.raises(ValueError, match="transport\\[cde-asu\\].*source_url"):
        parse_transport(json.dumps([raw]))


def test_negative_minutes_are_rejected():
    with pytest.raises(ValueError, match="transport\\[cde-asu\\]"):
        parse_transport(json.dumps([route(minutes=-1)]))


def test_rail_accepts_null_values_and_strings():
    raw = rail(fee_fixed={"amount": "0", "currency": "BRL"}, fee_pct="0.0035", iof_pct="0.0038")
    parsed = parse_rails(json.dumps([raw]))
    r = parsed["pix-br-bank-revolut-brl"]
    assert r.fee_fixed is not None and r.fee_fixed.amount == D(0)
    assert r.fee_pct == D("0.0035")
    assert r.iof_pct == D("0.0038")


def test_rail_rejects_unknown_currency_with_the_line_id():
    with pytest.raises(ValueError, match="rails\\[pix-br-bank-revolut-brl\\]"):
        parse_rails(json.dumps([rail(currency="EUR")]))


def test_rail_rejects_fee_pct_out_of_range():
    with pytest.raises(ValueError, match="rails\\[pix-br-bank-revolut-brl\\]"):
        parse_rails(json.dumps([rail(fee_pct="1.5")]))


def test_rail_rejects_duplicate_ids():
    with pytest.raises(ValueError, match="duplicad"):
        parse_rails(json.dumps([rail(), rail()]))
