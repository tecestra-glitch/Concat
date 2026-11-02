from decimal import Decimal

import pytest

from fronteira_fx.engine.positions import Balance, Position

D = Decimal


def test_balance_lifecycle():
    b = Balance(free=D("1000"))
    b = b.reserve(D("200"))
    assert b.available == D("800") and b.reserved == D("200")
    b = b.debit(D("200"), from_reserved=True)
    assert b.free == D("800") and b.reserved == 0
    b = b.send(D("300"))
    assert b.free == D("500") and b.in_transit == D("300") and b.total == D("800")
    b = b.settle(D("300"))
    assert b.free == D("800") and b.in_transit == 0
    with pytest.raises(ValueError):
        b.debit(D("900"))


def test_position_dict_uses_string_decimals():
    p = Position("USD", institution="ueno", location="digital", modality="account")
    assert p.to_dict(D("1000.50")) == {
        "currency": "USD",
        "account_id": None,
        "institution": "ueno",
        "location": "digital",
        "modality": "account",
        "amount": "1000.5",
    }
    assert "ueno" in p.label()
