from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Literal

Confidence = Literal["quoted", "estimated", "incomplete"]
_ORDER: dict[str, int] = {"quoted": 0, "estimated": 1, "incomplete": 2}

ZERO = Decimal("0")
ONE = Decimal("1")


def node_key(currency: str, venue: str) -> str:
    return f"{currency}@{venue}"


def worst(a: Confidence, b: Confidence) -> Confidence:
    return a if _ORDER[a] >= _ORDER[b] else b


@dataclass(slots=True, frozen=True)
class Edge:
    """Uma forma de mover valor de `src` para `dst`.

    rate: unidades de dst por 1 unidade de src, antes de custos.
    fee_pct: custo proporcional sobre a ENTRADA (0.01 = 1 %).
    fee_fixed: custo fixo na moeda de SAÍDA.
    min_in / max_in: limites do montante de entrada (None = sem limite).
    minutes: prazo estimado. via: descrição legível. evidence_id: rastreabilidade.
    """

    src: str
    dst: str
    rate: Decimal
    fee_pct: Decimal = ZERO
    fee_fixed: Decimal = ZERO
    minutes: int = 0
    via: str = ""
    confidence: Confidence = "estimated"
    evidence_id: str | None = None
    min_in: Decimal | None = None
    max_in: Decimal | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "from": self.src,
            "to": self.dst,
            "rate": str(self.rate),
            "feePct": str(self.fee_pct),
            "feeFixed": str(self.fee_fixed),
            "minutes": self.minutes,
            "via": self.via,
            "confidence": self.confidence,
            "evidenceId": self.evidence_id,
        }


def apply_edge(amount: Decimal, e: Edge) -> Decimal | None:
    """Valor recebido ao passar `amount` pela aresta; None se fora dos limites."""
    if e.min_in is not None and amount < e.min_in:
        return None
    if e.max_in is not None and amount > e.max_in:
        return None
    return amount * (ONE - e.fee_pct) * e.rate - e.fee_fixed


@dataclass(slots=True)
class Cycle:
    start: str
    path: list[str]
    edges: list[Edge]
    amount_in: Decimal
    amount_out: Decimal
    minutes: int
    confidence: Confidence
    method: str = "enumeration"
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def gain(self) -> Decimal:
        return self.amount_out - self.amount_in

    @property
    def roi(self) -> Decimal:
        return self.gain / self.amount_in if self.amount_in else ZERO

    def to_dict(self) -> dict[str, Any]:
        return {
            "start": self.start,
            "path": self.path,
            "edges": [e.to_dict() for e in self.edges],
            "amountIn": str(self.amount_in),
            "amountOut": str(self.amount_out),
            "gain": str(self.gain),
            "roi": str(self.roi),
            "minutes": self.minutes,
            "confidence": self.confidence,
            "method": self.method,
            **self.extra,
        }
