"""Contrato de cidade: todo validador que aceita city precisa aceitar o mesmo conjunto da API (docs/api-contract.md)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import get_args

import pytest
from pydantic import ValidationError

from fronteira_fx.notify.rules import CITIES, AlertRuleIn
from fronteira_fx.schemas import City
from fronteira_fx.schemas_candles import HouseHours, HouseSession

API_CITIES = frozenset(c for c in get_args(City) if c is not None)


def test_alert_rule_city_set_matches_api_contract():
    assert CITIES == API_CITIES
    assert "FOZ" in CITIES


def test_house_city_set_matches_api_contract():
    from fronteira_fx.schemas_candles import HouseCity

    assert frozenset(get_args(HouseCity)) == API_CITIES


@pytest.mark.parametrize("city", sorted(API_CITIES))
def test_quote_move_rule_accepts_each_api_city(city):
    rule = AlertRuleIn.model_validate(
        {"name": "x", "kind": "quote_move", "threshold": Decimal("0.01"), "params": {"pair": "USD/BRL", "city": city}}
    )
    assert rule.params == {"pair": "USD/BRL", "city": city}


@pytest.mark.parametrize("city", sorted(API_CITIES))
def test_opportunity_rule_accepts_each_api_city(city):
    rule = AlertRuleIn.model_validate(
        {"name": "x", "kind": "opportunity_new", "threshold": Decimal("0"), "params": {"channel": "physical", "city": city}}
    )
    assert rule.params == {"channel": "physical", "city": city}


def test_quote_move_rule_still_rejects_unknown_city():
    with pytest.raises(ValidationError, match="city"):
        AlertRuleIn.model_validate(
            {"name": "x", "kind": "quote_move", "threshold": Decimal("0.01"), "params": {"pair": "USD/BRL", "city": "XXX"}}
        )


def test_house_session_accepts_foz_physical_house():
    session = HouseSession.model_validate(
        {
            "source_id": "atlas",
            "name": "Atlas Câmbio",
            "city": "FOZ",
            "tz": "America/Asuncion",
            "channel": "physical",
            "reference": False,
            "status": "open",
            "opens_at": datetime(2026, 11, 4, 12, 0, tzinfo=UTC),
            "closes_at": datetime(2026, 11, 4, 20, 0, tzinfo=UTC),
            "next_change_at": None,
            "data_mode": "real",
        }
    )
    assert session.city == "FOZ"


def test_house_hours_accepts_foz_physical_house():
    hours = HouseHours.model_validate({"city": "FOZ", "tz": "America/Sao_Paulo", "days": [1, 2, 3, 4, 5], "opens": "09:00", "closes": "18:00"})
    assert hours.city == "FOZ"
