"""Decimal helpers. All money math uses `decimal.Decimal` with precision 28.

Rounding (ROUND_HALF_EVEN) happens only at presentation time via `fmt`.
"""

from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal, getcontext
from typing import Any

getcontext().prec = 28

ZERO = Decimal(0)
ONE = Decimal(1)
PRESENTATION_PLACES = 8


def D(value: Any) -> Decimal:
    """Build a Decimal without binary-float artefacts (floats go through `str`)."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        return Decimal(repr(value))
    return Decimal(str(value))


def fmt(value: Decimal | None, places: int | None = PRESENTATION_PLACES) -> str | None:
    """Canonical string for a Decimal: fixed notation, trailing zeros stripped.

    `places` quantizes (banker's rounding) before formatting; None keeps the exact value.
    """
    if value is None:
        return None
    v = Decimal(value)
    if not v.is_finite():
        return str(v)
    if places is not None:
        v = v.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_EVEN)
    s = format(v, "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    if s in ("", "-0"):
        s = "0"
    return s


def sign(value: Decimal | None) -> str:
    if value is None:
        return "none"
    if value > 0:
        return "+"
    if value < 0:
        return "-"
    return "0"
