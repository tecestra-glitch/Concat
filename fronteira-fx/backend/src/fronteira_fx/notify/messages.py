"""Textos das notificações em pt-BR e formatação de valores (vírgula decimal, ponto de milhar).

Exemplo: `cycle_text(...)` -> "Ciclo BRL@brbank → PYG@ueno → USD@ueno → BRL@brbank: +R$ 41,20 (0,165 %) em 3,0 d".
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal

CURRENCY_SYMBOL: dict[str, str] = {"BRL": "R$", "USD": "US$", "PYG": "Gs"}
CURRENCY_PLACES: dict[str, int] = {"PYG": 0}  # guarani não tem centavos na prática
RATE_PLACES: dict[str, int] = {"PYG": 0}  # cotações de PYG por unidade: inteiro; demais: 4 casas
DEFAULT_RATE_PLACES = 4
_PT_TABLE = str.maketrans({",": ".", ".": ","})
_MAX_DETAIL = 200


def _sign_body(value: Decimal, places: int, signed: bool) -> tuple[str, str]:
    """Separa sinal e corpo numérico pt-BR, arredondando meio para cima."""
    rounded = value.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
    body = f"{abs(rounded):,.{places}f}".translate(_PT_TABLE)
    if rounded < 0:
        return "-", body
    if signed and rounded > 0:
        return "+", body
    return "", body


def fmt_money(value: Decimal, currency: str, *, signed: bool = False) -> str:
    """'+R$ 41,20', 'R$ 5.000,00', 'Gs 41.200'."""
    sign, body = _sign_body(value, CURRENCY_PLACES.get(currency, 2), signed)
    return f"{sign}{CURRENCY_SYMBOL.get(currency, currency)} {body}"


def fmt_pct(ratio: Decimal, *, signed: bool = False) -> str:
    """Fração -> percentual com 3 casas: 0.001648 -> '0,165 %'."""
    sign, body = _sign_body(ratio * 100, 3, signed)
    return f"{sign}{body} %"


def fmt_rate(value: Decimal, quote_currency: str) -> str:
    """Cotação sem sinal: '7.450' para PYG, '5,4123' para as demais."""
    places = RATE_PLACES.get(quote_currency, DEFAULT_RATE_PLACES)
    return _sign_body(value, places, signed=False)[1]


def fmt_duration(minutes: Decimal) -> str:
    """Prazo: '45 min', '5,0 h', '3,0 d'."""
    if minutes < 60:
        whole = minutes.quantize(Decimal(1), rounding=ROUND_HALF_UP)
        return f"{whole} min"
    if minutes < 1440:
        return f"{_sign_body(minutes / 60, 1, signed=False)[1]} h"
    return f"{_sign_body(minutes / 1440, 1, signed=False)[1]} d"


def _clip(text: str | None, limit: int = _MAX_DETAIL) -> str:
    if not text:
        return ""
    flat = " ".join(str(text).split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


def cycle_text(
    *,
    path: Sequence[str],
    gain: Decimal,
    roi: Decimal,
    minutes: Decimal,
    confidence: str,
    currency: str,
) -> str:
    route = " → ".join(path)
    text = f"Ciclo {route}: {fmt_money(gain, currency, signed=True)} ({fmt_pct(roi)}) em {fmt_duration(minutes)}"
    if confidence == "incomplete":
        text += " — incompleto (há custo pendente)"
    return text


def quote_move_text(
    *,
    base: str,
    quote: str,
    city: str | None,
    source_id: str,
    previous: Decimal,
    current: Decimal,
    ratio: Decimal,
) -> str:
    where = f"em {city}" if city else "digital"
    return (
        f"{base}/{quote} {where} ({source_id}): "
        f"{fmt_rate(previous, quote)} → {fmt_rate(current, quote)} {quote} por 1 {base} "
        f"({fmt_pct(ratio, signed=True)})"
    )


_SOURCE_STATE = {"blocked": "bloqueada", "error": "com erro"}


def source_down_text(*, label: str, health: str, detail: str | None) -> str:
    state = _SOURCE_STATE.get(health, f"em estado {health}")
    return f"Fonte {label} {state}. Detalhe: {_clip(detail) or 'sem detalhes'}"


def opportunity_text(
    *,
    title: str,
    net_gain: Decimal | None,
    roi: Decimal | None,
    capital: Decimal | None,
) -> str:
    details: list[str] = []
    if net_gain is not None:
        details.append(f"ganho líquido {fmt_money(net_gain, 'BRL', signed=True)}")
    if roi is not None:
        details.append(f"ROI {fmt_pct(roi, signed=True)}")
    if capital is not None:
        details.append(f"capital {fmt_money(capital, 'BRL')}")
    text = f"Nova oportunidade no ranking principal: {_clip(title)}"
    return f"{text} — {', '.join(details)}" if details else text


def delivery_check_text(*, rule_name: str, channel: str) -> str:
    return f"Teste do alerta «{_clip(rule_name, 120)}» pelo canal {channel}: a entrega está funcionando."
