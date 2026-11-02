from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable, Mapping
from decimal import Decimal

from .model import ONE, Cycle, Edge, apply_edge, worst


def find_cycles(
    edges: Iterable[Edge],
    balances: Mapping[str, Decimal],
    *,
    max_len: int = 4,
    min_roi: Decimal | None = None,
) -> list[Cycle]:
    """Enumeração exata de ciclos simples (2..max_len arestas) a partir de cada nó com saldo.

    Avalia cada ciclo com o montante real (saldo livre do nó inicial), por isso custos fixos
    e limites de montante são respeitados. Ordena por ROI decrescente.
    """
    out: dict[str, list[Edge]] = defaultdict(list)
    for e in edges:
        out[e.src].append(e)
    found: list[Cycle] = []

    def walk(
        start: str, node: str, amount: Decimal, path: list[str], used: list[Edge], minutes: int, conf: str
    ) -> None:
        if len(used) >= max_len:
            return
        for e in out.get(node, []):
            if e.dst == start:
                if not used:
                    continue  # uma aresta só não é ciclo
                final = apply_edge(amount, e)
                if final is None:
                    continue
                c = Cycle(
                    start,
                    [*path, start],
                    [*used, e],
                    balances[start],
                    final,
                    minutes + e.minutes,
                    worst(conf, e.confidence),
                )  # type: ignore[arg-type]
                if min_roi is None or c.roi >= min_roi:
                    found.append(c)
                continue
            if e.dst in path:
                continue
            nxt = apply_edge(amount, e)
            if nxt is None or nxt <= 0:
                continue
            walk(start, e.dst, nxt, [*path, e.dst], [*used, e], minutes + e.minutes, worst(conf, e.confidence))  # type: ignore[arg-type]

    for start, amount in balances.items():
        if amount > 0:
            walk(start, start, amount, [start], [], 0, "quoted")
    found.sort(key=lambda c: c.roi, reverse=True)
    return found


def bellman_ford_negative_cycles(
    edges: Iterable[Edge], balances: Mapping[str, Decimal], *, max_len: int = 8
) -> list[Cycle]:
    """Bellman-Ford sobre pesos w = −ln(rate·(1−fee_pct)), com super-fonte ligada a todo nó
    com saldo.

    Um ciclo de peso negativo significa produto das taxas > 1 (lucro antes de custos fixos).
    Serve para grafos grandes onde enumerar é caro; cada ciclo encontrado é re-avaliado com o
    montante real (custos fixos e limites) antes de ser devolvido. Ciclos que não passem por
    um nó com saldo são descartados: sem saldo estacionado não há como executá-los.
    """
    edge_list = [e for e in edges if e.rate > 0 and e.fee_pct < ONE]
    nodes = {e.src for e in edge_list} | {e.dst for e in edge_list} | set(balances)
    SRC = "__super_source__"
    dist: dict[str, float] = {n: math.inf for n in nodes}
    pred: dict[str, Edge | None] = {n: None for n in nodes}
    dist[SRC] = 0.0
    weighted = [(e, -math.log(float(e.rate) * (1.0 - float(e.fee_pct)))) for e in edge_list]
    for n, bal in balances.items():
        if bal > 0:
            dist[n] = 0.0
    relaxed_last: list[str] = []
    for _ in range(len(nodes)):
        relaxed_last = []
        for e, w in weighted:
            if dist[e.src] + w < dist[e.dst] - 1e-12:
                dist[e.dst] = dist[e.src] + w
                pred[e.dst] = e
                relaxed_last.append(e.dst)
        if not relaxed_last:
            break
    cycles: list[Cycle] = []
    seen: set[tuple[str, ...]] = set()
    for v in relaxed_last:
        # anda max_len passos para trás para entrar no ciclo, depois o extrai
        x = v
        for _ in range(len(nodes)):
            p = pred.get(x)
            if p is None:
                break
            x = p.src
        cyc: list[Edge] = []
        y = x
        while True:
            p = pred.get(y)
            if p is None:
                break
            cyc.append(p)
            y = p.src
            if y == x or len(cyc) > max_len:
                break
        if not cyc or y != x:
            continue
        cyc.reverse()
        key = tuple(e.src for e in cyc)
        if key in seen:
            continue
        seen.add(key)
        # escolhe como início um nó do ciclo com saldo
        starts = [i for i, e in enumerate(cyc) if balances.get(e.src, Decimal(0)) > 0]
        if not starts:
            continue
        i0 = starts[0]
        ordered = cyc[i0:] + cyc[:i0]
        start = ordered[0].src
        amount = balances[start]
        cur: Decimal | None = amount
        conf = "quoted"
        minutes = 0
        for e in ordered:
            cur = apply_edge(cur, e) if cur is not None else None
            conf = worst(conf, e.confidence)  # type: ignore[arg-type]
            minutes += e.minutes
        if cur is None:
            continue
        cycles.append(
            Cycle(start, [e.src for e in ordered] + [start], ordered, amount, cur, minutes, conf, method="bellman_ford")
        )  # type: ignore[arg-type]
    cycles.sort(key=lambda c: c.roi, reverse=True)
    return cycles


def roi_per_day(c: Cycle) -> Decimal:
    minutes = max(1, c.minutes)
    return c.roi * (Decimal(1440) / Decimal(minutes))
