"""'Looks like a quote' score for a captured response. Pure: no I/O, no network.

Signals (max 100 in total):
  - currency codes present (USD, PYG, BRL, EUR, ARS, plus Gs./R$/US$ symbols)      up to 30
  - quote vocabulary (compra, venta, venda, buy, sell, cotización, tipo de cambio)   up to 30
  - rate-like numbers (5.944,76 / 7350 / 5.4437 / 1.100,01)                          up to 30
  - structured payload (JSON) with a quote vocabulary gets a small bonus              10
A score is a ranking hint, not proof: the report also shows the excerpt and whether a plain HTTP replay works.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_CURRENCY = re.compile(r"(?<![A-Za-z])(USD|PYG|BRL|EUR|ARS)(?![A-Za-z])|\b(Gs\.?|R\$|US\$)")
_VOCAB = {
    "compra": re.compile(r"(?i)\bcompra\b"),
    "venta": re.compile(r"(?i)\bventa\b"),
    "venda": re.compile(r"(?i)\bvenda\b"),
    "buy": re.compile(r"(?i)\bbuy\b"),
    "sell": re.compile(r"(?i)\bsell\b"),
    "cotizacion": re.compile(r"(?i)\bcotiza\w*|\bcotação|\bcotacao\b"),
    "tipo de cambio": re.compile(r"(?i)tipo de cambio|tipo de câmbio|taxa de câmbio"),
}
# 1.234,56 | 1,234.56 | 5944.76 | 7350 | 5,4437  (4+ digits or a decimal part)
_RATE = re.compile(
    r"(?<![\w.,])\d{1,3}(?:[.,]\d{3})+(?:[.,]\d{1,4})?(?![\w.,])"
    r"|(?<![\w.,])\d{1,6}[.,]\d{1,4}(?![\w.,])"
    r"|(?<![\w.,])\d{4,6}(?![\w.,])"
)


@dataclass(slots=True)
class Score:
    total: int
    reasons: list[str] = field(default_factory=list)


def score_text(text: str, *, is_json: bool = False) -> Score:
    if not text.strip():
        return Score(0, ["corpo vazio"])
    reasons: list[str] = []
    total = 0

    currencies = {m.group(1) or m.group(2) for m in _CURRENCY.finditer(text)}
    if currencies:
        pts = min(30, 10 * len(currencies))
        total += pts
        reasons.append(f"moedas {', '.join(sorted(currencies))} (+{pts})")

    vocab = [name for name, rx in _VOCAB.items() if rx.search(text)]
    if vocab:
        pts = min(30, 10 * len(vocab))
        total += pts
        reasons.append(f"vocabulário de cotação: {', '.join(vocab)} (+{pts})")

    rates = len(_RATE.findall(text))
    if rates:
        pts = min(30, 3 * rates)
        total += pts
        reasons.append(f"{rates} número(s) com cara de taxa (+{pts})")

    if is_json and vocab and (currencies or rates):
        total += 10
        reasons.append("JSON estruturado com cotação (+10)")

    return Score(min(total, 100), reasons)
