"""Position graph: nodes are `<currency>@<venue>`, edges are quotes/transfers/deposits/withdrawals.

Simple cycles of 2..max_len edges starting (and ending) at a node with a parked balance are evaluated
by folding the edges: `x = x * (1 - fee_pct) * rate - fee_fixed`. Pure Decimal, deterministic.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Literal

from ..decimal_utils import ONE, ZERO, fmt
from .routes import Confidence, combine_confidence

EdgeKind = Literal["quote", "transfer", "deposit", "withdraw"]


def node(currency: str, venue: str) -> str:
    return f"{currency}@{venue}"


def node_currency(n: str) -> str:
    return n.split("@", 1)[0]


@dataclass(frozen=True, slots=True)
class Edge:
    src: str
    dst: str
    kind: EdgeKind
    rate: Decimal  # dst currency per 1 src currency (1 for same-currency moves)
    fee_pct: Decimal = ZERO  # on the input amount
    fee_fixed: Decimal = ZERO  # in the output currency
    minutes: int = 0
    via: str = ""
    confidence: Confidence = "estimated"
    evidence_id: str | None = None
    # amount window (in the source currency) the quote is valid for; None = unbounded
    min_in: Decimal | None = None
    max_in: Decimal | None = None

    def apply(self, amount: Decimal) -> Decimal:
        return amount * (ONE - self.fee_pct) * self.rate - self.fee_fixed

    def accepts(self, amount: Decimal) -> bool:
        """True when `amount` (in the source currency) is inside the edge's amount window."""
        if self.min_in is not None and amount < self.min_in:
            return False
        if self.max_in is not None and amount > self.max_in:
            return False
        return True

    def to_dict(self) -> dict[str, Any]:
        """Contract shape (D1): snake_case, money as decimal strings."""
        return {
            "from": self.src,
            "to": self.dst,
            "kind": self.kind,
            "rate": fmt(self.rate),
            "fee_pct": fmt(self.fee_pct),
            "fee_fixed": fmt(self.fee_fixed),
            "minutes": self.minutes,
            "via": self.via,
            "confidence": self.confidence,
            "evidence_id": self.evidence_id,
        }


@dataclass(frozen=True, slots=True)
class Cycle:
    start: str
    path: tuple[str, ...]
    edges: tuple[Edge, ...]
    amount_in: Decimal
    amount_out: Decimal
    minutes: int
    confidence: Confidence

    @property
    def gain(self) -> Decimal:
        return self.amount_out - self.amount_in

    @property
    def roi(self) -> Decimal:
        return self.gain / self.amount_in if self.amount_in else ZERO

    def to_dict(self) -> dict[str, Any]:
        """Contract shape (D1): snake_case, money as decimal strings. `data_mode` is added by the API layer."""
        return {
            "start": self.start,
            "path": list(self.path),
            "edges": [e.to_dict() for e in self.edges],
            "amount_in": fmt(self.amount_in),
            "amount_out": fmt(self.amount_out),
            "gain": fmt(self.gain),
            "roi": fmt(self.roi),
            "minutes": self.minutes,
            "confidence": self.confidence,
        }


@dataclass(slots=True)
class Graph:
    edges: list[Edge] = field(default_factory=list)
    _out: dict[str, list[Edge]] = field(default_factory=dict, repr=False)

    def add(self, edge: Edge) -> None:
        if edge.rate <= 0 or edge.src == edge.dst:
            return
        self.edges.append(edge)
        self._out.setdefault(edge.src, []).append(edge)

    def extend(self, edges: Iterable[Edge]) -> None:
        for e in edges:
            self.add(e)

    @property
    def nodes(self) -> set[str]:
        s: set[str] = set()
        for e in self.edges:
            s.add(e.src)
            s.add(e.dst)
        return s

    def out_edges(self, n: str) -> list[Edge]:
        return sorted(self._out.get(n, []), key=lambda e: (e.dst, -e.rate, e.via))

    def evaluate(self, start: str, edges: tuple[Edge, ...], amount_in: Decimal) -> Cycle:
        x = amount_in
        for e in edges:
            x = e.apply(x)
        path = (start, *(e.dst for e in edges))
        return Cycle(
            start=start,
            path=path,
            edges=edges,
            amount_in=amount_in,
            amount_out=x,
            minutes=sum(e.minutes for e in edges),
            confidence=combine_confidence(*(e.confidence for e in edges)),
        )

    def simple_cycles_from(
        self, start: str, *, max_len: int = 4, min_len: int = 2, amount_in: Decimal | None = None
    ) -> list[tuple[Edge, ...]]:
        """All simple cycles (no repeated node) of min_len..max_len edges that return to `start`.

        With `amount_in`, the amount is folded along the trail and an edge whose `min_in`/`max_in`
        window does not accept the amount reaching it is discarded (a quote for 25 000 BRL is not
        valid for 5 000 BRL)."""
        found: list[tuple[Edge, ...]] = []

        def dfs(current: str, visited: set[str], trail: list[Edge], x: Decimal | None) -> None:
            for e in self.out_edges(current):
                if x is not None and not e.accepts(x):
                    continue
                if e.dst == start:
                    if len(trail) + 1 >= min_len:
                        found.append((*trail, e))
                    continue
                if e.dst in visited or len(trail) + 1 >= max_len:
                    continue
                visited.add(e.dst)
                trail.append(e)
                dfs(e.dst, visited, trail, e.apply(x) if x is not None else None)
                trail.pop()
                visited.discard(e.dst)

        dfs(start, {start}, [], amount_in)
        return found


def find_cycles(
    graph: Graph,
    balances: Mapping[str, Decimal],
    *,
    max_len: int = 4,
    min_roi: Decimal | None = None,
    limit: int = 200,
) -> list[Cycle]:
    """Evaluate cycles from every node with a positive free balance; best ROI first (deterministic)."""
    max_len = max(2, min(int(max_len), 6))
    out: list[Cycle] = []
    for start in sorted(balances):
        amount = balances[start]
        if amount is None or amount <= 0 or start not in graph.nodes:
            continue
        for edges in graph.simple_cycles_from(start, max_len=max_len, amount_in=amount):
            cyc = graph.evaluate(start, edges, amount)
            if min_roi is not None and cyc.roi < min_roi:
                continue
            out.append(cyc)
    out.sort(key=lambda c: (-c.roi, c.minutes, len(c.edges), c.start, c.path))
    return out[:limit]
