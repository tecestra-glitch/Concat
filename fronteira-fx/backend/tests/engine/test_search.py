from decimal import Decimal

from fronteira_fx.engine.search import DEFAULT_AMOUNTS, Evaluation, adaptive_amount_search

D = Decimal


def test_coarse_grid_only_when_nothing_changes():
    calls = []

    def evaluate(a):
        calls.append(a)
        return Evaluation(amount=a, winner="wu>chaco", roi=D("0.001"))

    res = adaptive_amount_search(evaluate)
    assert res.amounts_tested == list(DEFAULT_AMOUNTS)
    assert res.boundaries == []
    assert calls == list(DEFAULT_AMOUNTS)


def test_bisects_where_winner_changes_and_respects_budget():
    def evaluate(a):
        # winner flips at 17 500 BRL, roi sign flips at 40 000
        winner = "A" if a < D("17500") else "B"
        roi = D("0.002") if a < D("40000") else D("-0.001")
        return Evaluation(amount=a, winner=winner, roi=roi)

    res = adaptive_amount_search(evaluate, max_evaluations=12)
    assert len(res.amounts_tested) <= 12
    assert len(res.amounts_tested) > 4  # bisection happened
    kinds = {b.reason for b in res.boundaries}
    assert "winner_changes" in kinds and "roi_sign_changes" in kinds
    winner_b = next(b for b in res.boundaries if b.reason == "winner_changes")
    assert winner_b.low < D("17500") <= winner_b.high
    assert winner_b.high - winner_b.low <= D("250") or not winner_b.refined
    roi_b = next(b for b in res.boundaries if b.reason == "roi_sign_changes")
    assert roi_b.low < D("40000") <= roi_b.high
    assert roi_b.low_roi_sign == "+" and roi_b.high_roi_sign == "-"


def test_only_supported_amounts_are_evaluated():
    supported = {D("5000"), D("25000")}
    seen = []

    def evaluate(a):
        seen.append(a)
        return Evaluation(amount=a, winner="X" if a < D("20000") else "Y", roi=D("0.001"))

    res = adaptive_amount_search(evaluate, supports=lambda a: a in supported)
    assert set(seen) == supported  # midpoints unsupported => no bisection
    assert len(res.boundaries) == 1 and res.boundaries[0].refined is False


def test_search_is_deterministic():
    def evaluate(a):
        return Evaluation(amount=a, winner="A" if a < D("30000") else None, roi=D("0.001") if a < D("30000") else None)

    r1 = adaptive_amount_search(evaluate).to_dict()
    r2 = adaptive_amount_search(evaluate).to_dict()
    assert r1 == r2
    assert r1["boundaries"][0]["high_winner"] is None
