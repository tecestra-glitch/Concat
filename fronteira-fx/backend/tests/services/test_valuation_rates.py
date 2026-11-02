"""SEC-06: the valuation rate comes from the central bank (BCP), never from a third-party aggregator (dolarPy)
while BCP is present, and the choice does not depend on the order the quotes arrive in."""

from __future__ import annotations

from decimal import Decimal

from fronteira_fx.models import Quote
from fronteira_fx.services.opportunities import derive_valuation_rates

D = Decimal


def _q(source_id: str, buy: str, sell: str, *, kind: str, channel: str, modality: str) -> Quote:
    return Quote(
        source_id=source_id, base="USD", quote="PYG", buy=D(buy), sell=D(sell),
        kind=kind, channel=channel, modality=modality, city=None,
    )


BCP = _q("bcp", "7300", "7320", kind="market_reference", channel="digital", modality="transfer")
DOLARPY = _q("dolarpy", "7000", "7100", kind="market_reference", channel="aggregator", modality="reference")
UENO = _q("ueno", "7250", "7350", kind="indicative", channel="digital", modality="account")


def test_bcp_wins_over_dolarpy_in_any_order():
    for quotes in ([BCP, DOLARPY], [DOLARPY, BCP], [DOLARPY, UENO, BCP]):
        assert derive_valuation_rates(quotes, "PYG") == {"USD": D("7310")}


def test_aggregator_is_the_last_resort():
    assert derive_valuation_rates([DOLARPY, UENO], "PYG") == {"USD": D("7300")}
    assert derive_valuation_rates([DOLARPY], "PYG") == {"USD": D("7050")}


def test_ties_are_broken_by_source_id_not_arrival_order():
    other = _q("abc-ref", "7400", "7420", kind="market_reference", channel="digital", modality="transfer")
    assert derive_valuation_rates([BCP, other], "PYG") == derive_valuation_rates([other, BCP], "PYG") == {"USD": D("7410")}
