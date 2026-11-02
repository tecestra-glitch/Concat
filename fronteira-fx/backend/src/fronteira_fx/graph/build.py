"""Constrói arestas a partir de cotações normalizadas (dicts no formato do contrato)."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from decimal import Decimal
from typing import Any

from .model import ZERO, Edge, node_key

VenueOf = Callable[[dict[str, Any]], str]


def default_venue(q: dict[str, Any]) -> str:
    city = q.get("city")
    return f"{q['source_id']}:{city}" if city else str(q["source_id"])


def _dec(v: Any) -> Decimal | None:
    if v is None or v == "":
        return None
    d = Decimal(str(v))
    return d if d > 0 else None


def edges_from_quotes(quotes: Iterable[dict[str, Any]], venue_of: VenueOf = default_venue) -> list[Edge]:
    """Compra da fonte: base→quote a `buy`. Venda da fonte: quote→base a 1/`sell`.

    Referências de mercado (BCP, PTAX: `kind=market_reference` ou `modality=reference`) não são
    executáveis e são ignoradas (B23). Cotações que dependem do montante (`amount_base`) viram
    arestas com min_in = max_in = amount_base, para que o valor só seja usado no montante cotado.
    """
    out: list[Edge] = []
    for q in quotes:
        if q.get("kind") == "market_reference" or q.get("modality") == "reference":
            continue
        venue = venue_of(q)
        base, quote = str(q["base"]), str(q["quote"])
        minutes = 0 if q.get("modality") == "cash" else 1
        conf = "quoted" if q.get("kind") == "executable" else "estimated"
        pct = ZERO
        for f in q.get("fees") or []:
            if "%" in str(f.get("label", "")):
                pct += Decimal(str(f["amount"])) / Decimal("100")
        amount = _dec(q.get("amount_base"))
        buy, sell = _dec(q.get("buy")), _dec(q.get("sell"))
        ev = q.get("evidence_id")
        if buy is not None:
            out.append(
                Edge(
                    node_key(base, venue),
                    node_key(quote, venue),
                    buy,
                    pct,
                    ZERO,
                    minutes,
                    f"{q['source_id']} compra {base}",
                    conf,
                    ev,
                    amount,
                    amount,
                )
            )
        if sell is not None:
            out.append(
                Edge(
                    node_key(quote, venue),
                    node_key(base, venue),
                    Decimal(1) / sell,
                    pct,
                    ZERO,
                    minutes,
                    f"{q['source_id']} vende {base}",
                    conf,
                    ev,
                )
            )
    return out
