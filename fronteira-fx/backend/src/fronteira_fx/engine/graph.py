"""Position graph: nodes are `<currency>@<venue>`, edges are quotes/transfers/deposits/withdrawals.

Simple cycles starting (and ending) at a node with a parked balance are evaluated by folding the edges:
`x = x * (1 - fee_pct - iof_pct) * rate - fee_fixed - transport_fixed`. Pure Decimal, deterministic.

`max_len` counts LEGS (trocas, transferências, deslocamentos, saques ATM), not balcão walk-ins: an edge with
`counter=True` (ida ao caixa de uma casa da mesma cidade) is free of depth, so a route that buys dollars in one
house and sells them in another in the same city (or carries cash from one city to another) fits in max_len=4.

A cost the engine cannot price is never zero: the edge lists it in `unknown` and `leg_costs` returns None for it.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Literal

from ..decimal_utils import ONE, ZERO, fmt
from .routes import Confidence, combine_confidence

EdgeKind = Literal["quote", "transfer", "deposit", "withdraw", "travel"]
LegKind = Literal["exchange", "transfer", "travel", "deposit", "withdraw"]
Channel = Literal["presencial", "assistida", "automatizavel"]
# Nome da perna para o usuário: a aresta `quote` é uma troca; as demais mantêm o nome da aresta.
LEG_KIND: dict[str, LegKind] = {
    "quote": "exchange",
    "transfer": "transfer",
    "travel": "travel",
    "deposit": "deposit",
    "withdraw": "withdraw",
}
COST_KEYS = ("spread", "fees", "iof", "transport")


def node(currency: str, venue: str) -> str:
    return f"{currency}@{venue}"


def node_currency(n: str) -> str:
    return n.split("@", 1)[0]


@dataclass(frozen=True, slots=True)
class LegCosts:
    """Custos de uma perna, na moeda de origem da perna. None = desconhecido (nunca zero)."""

    spread: Decimal | None
    fees: Decimal | None
    iof: Decimal | None
    transport: Decimal | None

    def as_dict(self, currency: str) -> dict[str, Any]:
        return {
            "currency": currency,
            "spread": _opt(self.spread),
            "fees": _opt(self.fees),
            "iof": _opt(self.iof),
            "transport": _opt(self.transport),
        }


def _opt(value: Decimal | None) -> str | None:
    return fmt(value) if value is not None else None


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
    iof_pct: Decimal = ZERO  # IOF on the input amount (BRL convertido por instituição brasileira)
    transport_fixed: Decimal = ZERO  # custo de deslocamento, na moeda de saída (travel: a mesma moeda)
    # taxa de referência (valoração) na mesma unidade de `rate`; mede o spread. None = desconhecida.
    mid_rate: Decimal | None = None
    channel: Channel = "presencial"
    border: bool = False  # a perna cruza a fronteira BR↔PY
    # balcão (ida ao caixa de uma casa na mesma cidade): não conta no limite de pernas (`max_len`)
    counter: bool = False
    # categorias de custo que o motor não consegue precificar (⊆ COST_KEYS). Os valores ZERO guardados nelas
    # são só placeholders: `leg_costs` devolve None e a aresta é sempre `incomplete`.
    unknown: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        stray = set(self.unknown) - set(COST_KEYS)
        if stray:
            raise ValueError(f"custo desconhecido inválido: {sorted(stray)}")
        if self.unknown and self.confidence != "incomplete":
            object.__setattr__(self, "confidence", "incomplete")

    def apply(self, amount: Decimal) -> Decimal:
        return amount * (ONE - self.fee_pct - self.iof_pct) * self.rate - self.fee_fixed - self.transport_fixed

    def leg_costs(self, amount: Decimal) -> LegCosts:
        """Custos da perna convertidos para a moeda de origem (`amount` nessa moeda). Desconhecido = None."""
        unknown = self.unknown
        spread = None
        if "spread" not in unknown and self.mid_rate:
            spread = amount * (ONE - self.rate / self.mid_rate)
        return LegCosts(
            spread=spread,
            fees=None if "fees" in unknown else amount * self.fee_pct + self.fee_fixed / self.rate,
            iof=None if "iof" in unknown else amount * self.iof_pct,
            transport=None if "transport" in unknown else self.transport_fixed / self.rate,
        )

    def accepts(self, amount: Decimal) -> bool:
        """True when `amount` (in the source currency) is inside the edge's amount window."""
        if self.min_in is not None and amount < self.min_in:
            return False
        if self.max_in is not None and amount > self.max_in:
            return False
        return True

    def to_dict(self) -> dict[str, Any]:
        """Contract shape (D1): snake_case, money as decimal strings. Aplicar estes campos reproduz `amount_out`:
        `x * (1 - fee_pct - iof_pct) * rate - fee_fixed - transport_fixed`, a cada aresta, na ordem do ciclo."""
        return {
            "from": self.src,
            "to": self.dst,
            "kind": self.kind,
            "rate": fmt(self.rate),
            "fee_pct": fmt(self.fee_pct),
            "fee_fixed": fmt(self.fee_fixed),
            "iof_pct": fmt(self.iof_pct),
            "transport_fixed": fmt(self.transport_fixed),
            "minutes": self.minutes,
            "via": self.via,
            "confidence": self.confidence,
            "evidence_id": self.evidence_id,
            "channel": self.channel,
            "border": self.border,
            "counter": self.counter,
            "ref_rate": _opt(self.mid_rate),
            "unknown_costs": [k for k in COST_KEYS if k in self.unknown],
        }


@dataclass(frozen=True, slots=True)
class Leg:
    """Uma perna executada por um ciclo, com montante de entrada/saída e custos na moeda de origem."""

    kind: LegKind
    channel: Channel
    src: str
    dst: str
    via: str
    minutes: int
    border: bool
    amount_in: Decimal
    amount_out: Decimal
    costs: LegCosts

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "channel": self.channel,
            "from": self.src,
            "to": self.dst,
            "via": self.via,
            "minutes": self.minutes,
            "border": self.border,
            "amount_in": fmt(self.amount_in),
            "amount_out": fmt(self.amount_out),
            "costs": self.costs.as_dict(node_currency(self.src)),
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
    legs: tuple[Leg, ...] = ()
    # preenchidos por `services.cycles.enrich_cycle` (precisam das taxas de valoração)
    gain_by_currency: dict[str, Decimal | None] | None = None
    costs: dict[str, Decimal | None] | None = None  # spread/fees/iof/transport, na moeda de partida
    requires_declaration: bool = False

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
            "legs": [leg.to_dict() for leg in self.legs],
            "amount_in": fmt(self.amount_in),
            "amount_out": fmt(self.amount_out),
            "gain": fmt(self.gain),
            "roi": fmt(self.roi),
            "gain_by_currency": _money_map(self.gain_by_currency),
            "costs": _money_map(self.costs),
            "requires_declaration": self.requires_declaration,
            "minutes": self.minutes,
            "confidence": self.confidence,
        }


def _money_map(values: dict[str, Decimal | None] | None) -> dict[str, str | None] | None:
    if values is None:
        return None
    return {k: (fmt(v) if v is not None else None) for k, v in values.items()}


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
        legs: list[Leg] = []
        for e in edges:
            out = e.apply(x)
            legs.append(
                Leg(
                    kind=LEG_KIND[e.kind],
                    channel=e.channel,
                    src=e.src,
                    dst=e.dst,
                    via=e.via,
                    minutes=e.minutes,
                    border=e.border,
                    amount_in=x,
                    amount_out=out,
                    costs=e.leg_costs(x),
                )
            )
            x = out
        path = (start, *(e.dst for e in edges))
        return Cycle(
            start=start,
            path=path,
            edges=edges,
            amount_in=amount_in,
            amount_out=x,
            minutes=sum(e.minutes for e in edges),
            confidence=combine_confidence(*(e.confidence for e in edges)),
            legs=tuple(legs),
        )

    def simple_cycles_from(
        self, start: str, *, max_len: int = 4, min_len: int = 2, amount_in: Decimal | None = None
    ) -> list[tuple[Edge, ...]]:
        """All simple cycles (no repeated node) that return to `start`, with at least `min_len` edges and at most
        `max_len` legs (balcão edges, `counter=True`, do not count as legs).

        With `amount_in`, the amount is folded along the trail and an edge whose `min_in`/`max_in`
        window does not accept the amount reaching it is discarded (a quote for 25 000 BRL is not
        valid for 5 000 BRL)."""
        found: list[tuple[Edge, ...]] = []

        def dfs(current: str, visited: set[str], trail: list[Edge], legs: int, x: Decimal | None) -> None:
            for e in self.out_edges(current):
                if x is not None and not e.accepts(x):
                    continue
                step = 0 if e.counter else 1
                if legs + step > max_len:
                    continue
                if e.dst == start:
                    if len(trail) + 1 >= min_len:
                        found.append((*trail, e))
                    continue
                if e.dst in visited:
                    continue
                visited.add(e.dst)
                trail.append(e)
                dfs(e.dst, visited, trail, legs + step, e.apply(x) if x is not None else None)
                trail.pop()
                visited.discard(e.dst)

        dfs(start, {start}, [], 0, amount_in)
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
    max_len = max(2, min(int(max_len), 6))  # pernas (balcão não conta)
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
