"""B15: stored fee JSON keeps a percentage component when the adapter provides one."""

from __future__ import annotations

from decimal import Decimal

from fronteira_fx.adapters.base import Fee
from fronteira_fx.schemas import FeeOut
from fronteira_fx.services.quotes import fees_to_json


def test_fees_to_json_keeps_pct_only_when_present():
    rows = fees_to_json(
        [
            Fee("tarifa", Decimal("9.90"), "BRL"),
            {"label": "spread", "amount": None, "pct": Decimal("0.015"), "currency": "BRL"},
        ]
    )
    assert rows[0] == {"label": "tarifa", "amount": "9.9", "currency": "BRL"}
    assert rows[1] == {"label": "spread", "amount": None, "pct": "0.015", "currency": "BRL"}
    # the API shape accepts both (stored rows are rebuilt with `FeeOut(**row)`)
    assert [FeeOut(**r).pct for r in rows] == [None, Decimal("0.015")]
