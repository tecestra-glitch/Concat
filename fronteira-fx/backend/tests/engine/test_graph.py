from decimal import Decimal

from fronteira_fx.engine.graph import Edge, Graph, find_cycles, node

D = Decimal


def triangle() -> Graph:
    g = Graph()
    g.add(Edge(node("BRL", "nubank"), node("BRL", "wu"), "deposit", D(1), minutes=10, via="pix"))
    g.add(
        Edge(
            node("BRL", "wu"),
            node("PYG", "ueno"),
            "quote",
            D("1380"),
            fee_fixed=D("0"),
            minutes=240,
            via="wu",
            confidence="quoted",
        )
    )
    g.add(
        Edge(
            node("PYG", "ueno"),
            node("USD", "ueno"),
            "quote",
            D(1) / D("7395"),
            minutes=5,
            via="ueno",
            confidence="estimated",
        )
    )
    g.add(Edge(node("USD", "ueno"), node("USD", "nomad"), "withdraw", D(1), minutes=60, via="transfer"))
    g.add(
        Edge(
            node("USD", "nomad"),
            node("BRL", "nubank"),
            "quote",
            D("5.372"),
            minutes=5,
            via="nomad",
            confidence="estimated",
        )
    )
    # a short 2-edge loop with a fee that makes it a loss
    g.add(
        Edge(
            node("BRL", "nubank"),
            node("USD", "nomad"),
            "quote",
            D(1) / D("5.418"),
            fee_pct=D("0.011"),
            minutes=5,
            via="nomad",
        )
    )
    return g


def test_simple_cycles_and_evaluation():
    g = triangle()
    start = node("BRL", "nubank")
    cycles = find_cycles(g, {start: D("5000")}, max_len=5)
    assert cycles, "expected at least the 5-edge loop and the 2-edge loop"
    paths = {c.path for c in cycles}
    assert ("BRL@nubank", "BRL@wu", "PYG@ueno", "USD@ueno", "USD@nomad", "BRL@nubank") in paths
    assert ("BRL@nubank", "USD@nomad", "BRL@nubank") in paths
    long = next(c for c in cycles if len(c.edges) == 5)
    expected = D("5000") * D("1380") * (D(1) / D("7395")) * D("5.372")
    assert long.amount_out == expected
    assert long.gain == expected - D("5000") and long.roi == long.gain / D("5000")
    assert long.minutes == 320 and long.confidence == "estimated"
    short = next(c for c in cycles if len(c.edges) == 2)
    assert short.gain < 0
    assert cycles[0].roi >= cycles[-1].roi  # best first


def test_max_len_min_roi_and_balances_filter():
    g = triangle()
    start = node("BRL", "nubank")
    assert all(len(c.edges) <= 3 for c in find_cycles(g, {start: D("5000")}, max_len=3))
    assert find_cycles(g, {start: D("0")}) == []
    assert find_cycles(g, {"USD@nowhere": D("10")}) == []
    positive = find_cycles(g, {start: D("5000")}, max_len=5, min_roi=D("0"))
    assert all(c.roi >= 0 for c in positive)
    d = positive[0].to_dict()
    assert set(d) == {"start", "path", "edges", "amountIn", "amountOut", "gain", "roi", "minutes", "confidence"}
    assert d["edges"][0]["from"] == "BRL@nubank" and isinstance(d["amountIn"], float)


def test_edge_apply_fee_semantics():
    e = Edge("A@x", "B@x", "quote", D("2"), fee_pct=D("0.01"), fee_fixed=D("3"))
    assert e.apply(D("100")) == D("100") * (D(1) - D("0.01")) * D("2") - D("3")
    g = Graph()
    g.add(Edge("A@x", "A@x", "transfer", D(1)))  # self loops ignored
    g.add(Edge("A@x", "B@x", "quote", D(0)))  # non-positive rates ignored
    assert g.edges == []
