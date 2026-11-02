from decimal import Decimal

from fastapi import FastAPI
from fastapi.testclient import TestClient

from fronteira_fx.graph import Edge, apply_edge, bellman_ford_negative_cycles, find_cycles, node_key, roi_per_day
from fronteira_fx.graph.build import edges_from_quotes
from fronteira_fx.graph.router import router, set_provider

D = Decimal


def e(src: str, dst: str, rate: str, **kw) -> Edge:
    return Edge(
        src,
        dst,
        D(rate),
        **{k: (D(v) if k in {"fee_pct", "fee_fixed", "min_in", "max_in"} else v) for k, v in kw.items()},
    )


def test_triangular_cycle_roi_with_parked_amount() -> None:
    edges = [
        e("USD@a", "PYG@a", "5975"),
        e("PYG@a", "BRL@a", str(D(1) / D(1086))),
        e("BRL@a", "USD@a", str(D(1) / D("5.40"))),
    ]
    cycles = find_cycles(edges, {"USD@a": D("1000")})
    assert len(cycles) == 1
    c = cycles[0]
    expected = D("1000") * D("5975") / D(1086) / D("5.40")
    assert abs(c.amount_out - expected) < D("0.0001")
    assert c.roi == c.gain / D("1000")
    assert c.roi > 0


def test_fees_applied_once_per_edge_and_limits() -> None:
    edge = e("a", "b", "2", fee_pct="0.01", fee_fixed="3")
    assert apply_edge(D("100"), edge) == D("100") * D("0.99") * D("2") - D("3")
    limited = e("a", "b", "2", min_in="500")
    assert apply_edge(D("100"), limited) is None


def test_single_edge_loop_and_repeated_nodes_are_ignored() -> None:
    cycles = find_cycles([e("a", "a", "1.5"), e("a", "b", "1"), e("b", "a", "1.01")], {"a": D("10")})
    assert all(len(c.edges) >= 2 for c in cycles)
    assert len(cycles) == 1


def test_worst_confidence_propagates_and_min_roi_filters() -> None:
    cycles = find_cycles([e("a", "b", "1", confidence="incomplete"), e("b", "a", "1.1")], {"a": D("10")})
    assert cycles[0].confidence == "incomplete"
    assert find_cycles([e("a", "b", "1"), e("b", "a", "1.001")], {"a": D("10")}, min_roi=D("0.01")) == []


def test_only_nodes_with_balance_start_cycles_and_sorted_by_roi() -> None:
    cycles = find_cycles(
        [e("a", "b", "1"), e("b", "a", "1.1"), e("a", "c", "1"), e("c", "a", "1.2")], {"a": D("5"), "b": D("0")}
    )
    assert {c.start for c in cycles} == {"a"}
    assert [c.roi for c in cycles] == sorted((c.roi for c in cycles), reverse=True)


def test_roi_per_day() -> None:
    (c,) = find_cycles([e("a", "b", "1", minutes=720), e("b", "a", "1.01", minutes=720)], {"a": D("100")})
    assert roi_per_day(c) == D("0.01")


def test_edges_from_quotes_directions_and_reference_skip() -> None:
    q = {
        "source_id": "s",
        "city": None,
        "base": "USD",
        "quote": "PYG",
        "buy": "5900",
        "sell": "5980",
        "modality": "account",
        "kind": "indicative",
        "fees": [],
        "evidence_id": "ev",
        "amount_base": None,
    }
    edges = edges_from_quotes([q, {**q, "kind": "market_reference"}])
    assert len(edges) == 2
    buy = next(x for x in edges if x.src == node_key("USD", "s"))
    sell = next(x for x in edges if x.src == node_key("PYG", "s"))
    assert buy.rate == D("5900") and buy.dst == "PYG@s"
    assert sell.rate == D(1) / D("5980")
    amt = edges_from_quotes([{**q, "amount_base": "5000", "sell": None}])
    assert amt[0].min_in == D("5000") == amt[0].max_in


def test_bellman_ford_finds_same_profitable_cycle() -> None:
    edges = [
        e("USD@a", "PYG@a", "5975"),
        e("PYG@a", "BRL@a", str(D(1) / D(1086))),
        e("BRL@a", "USD@a", str(D(1) / D("5.40"))),
        e("USD@a", "EUR@a", "0.9"),
        e("EUR@a", "USD@a", "1.05"),
    ]
    bf = bellman_ford_negative_cycles(edges, {"USD@a": D("1000")})
    assert bf and bf[0].method == "bellman_ford" and bf[0].roi > 0
    en = find_cycles(edges, {"USD@a": D("1000")})
    assert abs(bf[0].roi - en[0].roi) < D("0.000001")


def test_bellman_ford_no_cycle_without_balance() -> None:
    edges = [e("a", "b", "1"), e("b", "a", "1.1")]
    assert bellman_ford_negative_cycles(edges, {"z": D("1")}) == []


def test_router() -> None:
    set_provider(lambda: ([e("a", "b", "1"), e("b", "a", "1.1", minutes=5)], {"a": D("10")}))
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    r = client.get("/v1/opportunities/cycles?max_len=3&min_roi=0.05")
    assert r.status_code == 200
    body = r.json()
    assert body[0]["start"] == "a" and body[0]["roi"] == "0.1" and body[0]["minutes"] == 5
    assert client.get("/v1/opportunities/cycles?method=bellman_ford").json()[0]["method"] == "bellman_ford"
